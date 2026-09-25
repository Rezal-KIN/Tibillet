#!/usr/bin/env python3
"""Fail Foundation unless the exact newly requested Gala finished first boot."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path


REGION = "eu-west-3"
ACCOUNT = "318629836660"
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{1,62}\Z")


def aws(*args: str) -> dict[str, object]:
    result = subprocess.run(
        ["aws", *args, "--region", REGION, "--output", "json"],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def selected_instance(project: str, slug: str) -> str:
    response = aws(
        "ec2", "describe-instances", "--filters",
        f"Name=tag:Project,Values={project}",
        f"Name=tag:Gala,Values={slug}",
        "Name=instance-state-name,Values=running",
    )
    instances = [
        instance
        for reservation in response.get("Reservations", [])
        for instance in reservation.get("Instances", [])
    ]
    if len(instances) != 1:
        raise RuntimeError(f"expected exactly one running EC2 for {slug}, found {len(instances)}")
    instance = instances[0]
    tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}
    if tags.get("Project") != project or tags.get("Gala") != slug or tags.get("ManagedBy") != "terraform":
        raise RuntimeError("EC2 tags do not identify the requested Terraform Gala")
    return instance["InstanceId"]


def wait_online(instance_id: str) -> None:
    for _ in range(60):
        response = aws("ssm", "describe-instance-information", "--filters", f"Key=InstanceIds,Values={instance_id}")
        instances = response.get("InstanceInformationList", [])
        if len(instances) == 1 and instances[0].get("PingStatus") == "Online":
            return
        time.sleep(10)
    raise RuntimeError(f"SSM did not come online for {instance_id}")


def previously_registered(slug: str) -> bool:
    uri = os.environ.get("FOUNDATION_CATALOG_URI", "")
    if not uri.startswith("s3://") or not uri.endswith("/foundation-inputs/galas.json"):
        raise ValueError("Foundation catalog URI is missing or invalid")
    result = subprocess.run(
        ["aws", "s3", "cp", "--only-show-errors", uri, "-", "--region", REGION],
        check=True, capture_output=True, text=True,
    )
    catalog = json.loads(result.stdout)
    if catalog.get("version") != 1 or not isinstance(catalog.get("galas"), dict):
        raise ValueError("previous Foundation catalog is invalid")
    return slug in catalog["galas"]


def verify_command(instance_id: str, slug: str, *, require_clean_cloud_init: bool = True) -> None:
    # This reads no secret values and changes no runtime state. It must run
    # after cloud-init, so a Terraform-created but unbootstrapped host fails.
    commands = [
        "set -eu",
        f"test -f /etc/tibillet-gala/{slug}.conf",
        "test -x /usr/local/lib/tibillet-gala/install-runtime-contract.sh",
        "systemctl is-active --quiet docker",
        f"systemctl is-enabled --quiet tibillet-gala-stacks@{slug}.service",
    ]
    if require_clean_cloud_init:
        commands.insert(1, "cloud-init status --wait >/dev/null")
    response = aws(
        "ssm", "send-command", "--document-name", "AWS-RunShellScript",
        "--instance-ids", instance_id, "--parameters", json.dumps({"commands": commands}),
        "--timeout-seconds", "600",
    )
    command_id = response["Command"]["CommandId"]
    print(f"Bootstrap check: gala={slug} instance={instance_id} command={command_id}", flush=True)
    for _ in range(130):
        try:
            result = aws("ssm", "get-command-invocation", "--command-id", command_id, "--instance-id", instance_id)
        except subprocess.CalledProcessError as error:
            if "InvocationDoesNotExist" in error.stderr:
                time.sleep(5)
                continue
            raise
        status = result.get("Status")
        if status == "Success":
            print(f"Bootstrap verified: gala={slug} instance={instance_id}", flush=True)
            return
        if status not in {"Pending", "InProgress", "Delayed"}:
            raise RuntimeError(f"bootstrap check failed for {slug}: {status}; SSM command {command_id}")
        time.sleep(5)
    raise RuntimeError(f"bootstrap check timed out for {slug}; SSM command {command_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--project-name", required=True)
    args = parser.parse_args()
    if not SLUG.fullmatch(args.slug) or not SLUG.fullmatch(args.project_name):
        raise ValueError("invalid Gala slug or project name")
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    if catalog.get("version") != 1 or args.slug not in catalog.get("galas", {}):
        raise ValueError("requested Gala is absent from the approved catalog proposal")
    if aws("sts", "get-caller-identity").get("Account") != ACCOUNT:
        raise ValueError("wrong AWS account")
    instance_id = selected_instance(args.project_name, args.slug)
    wait_online(instance_id)
    # The committed catalog is updated only after this gate succeeds. A Gala
    # absent from it is a new/unfinished creation and must have a clean first
    # boot. Existing Galas are checked for the installed runtime and services,
    # without inheriting an old cloud-init error from their initial migration.
    verify_command(instance_id, args.slug, require_clean_cloud_init=not previously_registered(args.slug))


if __name__ == "__main__":
    main()
