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
RETIRED_DELIVERY_SLUGS = {"gala-smoke", "gala-validation", "gala-validation-2"}
VALIDATION_RETIREMENT = {
    "Prepare Validation Retirement": "prepare",
    "Retire Validation Instances": "retire",
}


def verify_validation_retirement(plan: dict[str, object], phase: str, project: str) -> None:
    """Check both exact hosts and their root volumes before committing catalog state."""
    active = aws("ssm", "get-parameter", "--name", f"/{project}/active-gala")
    if active.get("Parameter", {}).get("Value") in {"gala-validation", "gala-validation-2"}:
        raise RuntimeError("a validation Gala is currently active")
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ValueError("missing retirement plan changes")
    for slug in ("gala-validation", "gala-validation-2"):
        address = f'module.gala["{slug}"].aws_instance.retirable[0]'
        matches = [item for item in changes if isinstance(item, dict) and item.get("address") == address]
        if len(matches) != 1:
            raise RuntimeError(f"missing exact retirement plan target: {slug}")
        before = matches[0].get("change", {}).get("before")
        if not isinstance(before, dict):
            raise RuntimeError(f"missing prior EC2 state for {slug}")
        instance_id = before.get("id")
        blocks = before.get("root_block_device")
        if (not isinstance(instance_id, str) or not re.fullmatch(r"i-[0-9a-f]{8,17}", instance_id)
                or not isinstance(blocks, list) or len(blocks) != 1
                or not isinstance(blocks[0], dict)):
            raise RuntimeError(f"invalid EC2 or root volume in plan for {slug}")
        volume_id = blocks[0].get("volume_id")
        if not isinstance(volume_id, str) or not re.fullmatch(r"vol-[0-9a-f]{8,17}", volume_id):
            raise RuntimeError(f"invalid root volume in plan for {slug}")
        if phase == "prepare":
            found = aws("ec2", "describe-instances", "--instance-ids", instance_id)
            instances = [item for group in found.get("Reservations", []) for item in group.get("Instances", [])]
            if len(instances) != 1 or instances[0].get("State", {}).get("Name") != "running":
                raise RuntimeError(f"prepared EC2 is not running: {slug}")
            tags = {item["Key"]: item["Value"] for item in instances[0].get("Tags", [])}
            if tags.get("Project") != project or tags.get("Gala") != slug or tags.get("ManagedBy") != "terraform":
                raise RuntimeError(f"prepared EC2 identity mismatch: {slug}")
            protection = aws("ec2", "describe-instance-attribute", "--instance-id", instance_id,
                             "--attribute", "disableApiTermination")
            if protection.get("DisableApiTermination", {}).get("Value") is not False:
                raise RuntimeError(f"termination protection still enabled: {slug}")
            mappings = instances[0].get("BlockDeviceMappings", [])
            if not any(mapping.get("Ebs", {}).get("VolumeId") == volume_id
                       and mapping.get("Ebs", {}).get("DeleteOnTermination") is True
                       for mapping in mappings):
                raise RuntimeError(f"root volume will not be deleted on termination: {slug}")
            print(f"Validation retirement prepared: {slug} {instance_id}", flush=True)
        else:
            # EC2 termination and EBS deletion are asynchronous. No catalog
            # update is committed until both are absent.
            for _ in range(30):
                found = aws("ec2", "describe-instances", "--instance-ids", instance_id)
                instances = [item for group in found.get("Reservations", []) for item in group.get("Instances", [])]
                state = instances[0].get("State", {}).get("Name") if instances else "terminated"
                volumes = aws("ec2", "describe-volumes", "--filters", f"Name=volume-id,Values={volume_id}")
                if state == "terminated" and not volumes.get("Volumes", []):
                    break
                time.sleep(10)
            else:
                raise RuntimeError(f"validation EC2 or root volume still exists: {slug}")
            print(f"Validation retirement verified: {slug} {instance_id}", flush=True)


def is_delivery_retirement(plan: dict[str, object], slug: str) -> bool:
    """A historical pipeline cleanup must not depend on application health."""
    if slug not in RETIRED_DELIVERY_SLUGS:
        return False
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ValueError("Foundation plan has no resource_changes array")
    prefix = f'module.gala["{slug}"].'
    return all(
        not (isinstance(item, dict) and str(item.get("address", "")).startswith(prefix)
             and item.get("change", {}).get("actions") != ["no-op"])
        for item in changes
    )


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
    parser.add_argument("--foundation-plan", type=Path)
    args = parser.parse_args()
    if not SLUG.fullmatch(args.slug) or not SLUG.fullmatch(args.project_name):
        raise ValueError("invalid Gala slug or project name")
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    if catalog.get("version") != 1 or args.slug not in catalog.get("galas", {}):
        raise ValueError("requested Gala is absent from the approved catalog proposal")
    if aws("sts", "get-caller-identity").get("Account") != ACCOUNT:
        raise ValueError("wrong AWS account")
    retirement_phase = VALIDATION_RETIREMENT.get(os.environ.get("GALA_NAME", ""))
    if retirement_phase:
        if args.slug != "gala-validation" or not args.foundation_plan:
            raise ValueError("validation retirement requires the exact plan and slug")
        verify_validation_retirement(
            json.loads(args.foundation_plan.read_text(encoding="utf-8")),
            retirement_phase, args.project_name,
        )
        return
    instance_id = selected_instance(args.project_name, args.slug)
    wait_online(instance_id)
    if args.foundation_plan and is_delivery_retirement(
        json.loads(args.foundation_plan.read_text(encoding="utf-8")), args.slug
    ):
        print(f"Historical pipeline retirement: EC2 {instance_id} remains online; bootstrap check not applicable", flush=True)
        return
    # The committed catalog is updated only after this gate succeeds. A Gala
    # absent from it is a new/unfinished creation and must have a clean first
    # boot. Existing Galas are checked for the installed runtime and services,
    # without inheriting an old cloud-init error from their initial migration.
    verify_command(instance_id, args.slug, require_clean_cloud_init=not previously_registered(args.slug))


if __name__ == "__main__":
    main()
