#!/usr/bin/env python3
"""Plan or apply a reviewed switch of the one shared Gala EIP.

The plan is non-secret. Apply checks for drift, verifies the target locally by
SSM, moves the EIP and public ingress, verifies HTTPS, then records the active
slug in Parameter Store. A failed switch restores the previous association.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


ACCOUNT = "318629836660"
REGION = "eu-west-3"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def command(*arguments: str) -> str:
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({arguments[0]}): {result.stderr.strip()}")
    return result.stdout.strip()


def aws(*arguments: str) -> object:
    output = command("aws", *arguments, "--region", REGION, "--output", "json")
    return json.loads(output) if output else None


def context() -> dict[str, str]:
    names = {
        "project": "GALA_PROJECT_NAME",
        "catalog_uri": "FOUNDATION_CATALOG_URI",
        "allocation_id": "SHARED_EIP_ALLOCATION_ID",
        "public_group": "PUBLIC_SECURITY_GROUP_ID",
        "active_parameter": "ACTIVE_GALA_PARAMETER",
        "public_domain": "SHARED_GALA_DOMAIN",
    }
    values = {key: os.environ.get(name, "") for key, name in names.items()}
    if not all(values.values()):
        raise ValueError("switch project, catalog, EIP, security group, and active parameter must be configured")
    if os.environ.get("AWS_DEFAULT_REGION") != REGION:
        raise ValueError("switch must run in the Paris region")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", values["project"]):
        raise ValueError("invalid Gala project name")
    if not re.fullmatch(r"eipalloc-[0-9a-f]{8,17}", values["allocation_id"]):
        raise ValueError("invalid shared EIP allocation ID")
    if not re.fullmatch(r"sg-[0-9a-f]{8,17}", values["public_group"]):
        raise ValueError("invalid public security group ID")
    if values["active_parameter"] != f"/{values['project']}/active-gala":
        raise ValueError("unexpected active-Gala parameter name")
    if not re.fullmatch(r"[a-z0-9.-]+", values["public_domain"]):
        raise ValueError("invalid shared public domain")
    identity = aws("sts", "get-caller-identity")
    if not isinstance(identity, dict) or identity.get("Account") != ACCOUNT:
        raise ValueError("wrong AWS account for Gala switch")
    return values


def catalog_galas(uri: str) -> dict[str, object]:
    if not uri.startswith("s3://") or not uri.endswith("/foundation-inputs/galas.json"):
        raise ValueError("unexpected Foundation catalog URI")
    result = json.loads(command("aws", "s3", "cp", "--only-show-errors", uri, "-", "--region", REGION))
    if result.get("version") != 1 or not isinstance(result.get("galas"), dict):
        raise ValueError("invalid Foundation catalog")
    return result["galas"]


def instance(instance_id: str) -> dict[str, object]:
    response = aws("ec2", "describe-instances", "--instance-ids", instance_id)
    instances = [item for reservation in response["Reservations"] for item in reservation["Instances"]]
    if len(instances) != 1:
        raise ValueError("expected exactly one EC2 instance")
    return instances[0]


def primary_interface(host: dict[str, object]) -> dict[str, object]:
    interfaces = [
        item for item in host["NetworkInterfaces"]
        if item["Attachment"]["DeviceIndex"] == 0
    ]
    if len(interfaces) != 1:
        raise ValueError("expected one primary network interface")
    return interfaces[0]


def tags(host: dict[str, object]) -> dict[str, str]:
    return {item["Key"]: item["Value"] for item in host.get("Tags", [])}


def target_instance(project: str, slug: str) -> dict[str, object]:
    response = aws(
        "ec2", "describe-instances", "--filters",
        f"Name=tag:Project,Values={project}", f"Name=tag:Gala,Values={slug}",
        "Name=instance-state-name,Values=running",
    )
    instances = [item for reservation in response["Reservations"] for item in reservation["Instances"]]
    if len(instances) != 1 or tags(instances[0]).get("ManagedBy") != "terraform":
        raise ValueError("target Gala must have exactly one running Terraform EC2")
    online = aws("ssm", "describe-instance-information", "--filters", f"Key=InstanceIds,Values={instances[0]['InstanceId']}")
    if len(online["InstanceInformationList"]) != 1 or online["InstanceInformationList"][0]["PingStatus"] != "Online":
        raise ValueError("target Gala is not SSM Online")
    return instances[0]


def active_marker(name: str) -> str:
    response = aws("ssm", "get-parameter", "--name", name)
    value = response["Parameter"]["Value"]
    if value != "none" and not SLUG.fullmatch(value):
        raise ValueError("invalid active-Gala marker")
    return value


def address(allocation_id: str) -> dict[str, object]:
    response = aws("ec2", "describe-addresses", "--allocation-ids", allocation_id)
    if len(response["Addresses"]) != 1:
        raise ValueError("shared EIP allocation not found")
    return response["Addresses"][0]


def groups(interface: dict[str, object]) -> list[str]:
    return sorted(item["GroupId"] for item in interface["Groups"])


def build_plan(target_slug: str, settings: dict[str, str]) -> dict[str, object]:
    if not SLUG.fullmatch(target_slug) or target_slug == "bapts":
        raise ValueError("invalid target Gala slug")
    galas = catalog_galas(settings["catalog_uri"])
    if target_slug not in galas or galas[target_slug].get("create_instance") is not True:
        raise ValueError("target Gala is not enabled in the Foundation catalog")
    if galas[target_slug].get("domain") != settings["public_domain"]:
        raise ValueError("target Gala is not configured for the shared public domain")
    host = target_instance(settings["project"], target_slug)
    target_eni = primary_interface(host)
    eip = address(settings["allocation_id"])
    target_addresses = aws(
        "ec2", "describe-addresses", "--filters",
        f"Name=network-interface-id,Values={target_eni['NetworkInterfaceId']}",
    )["Addresses"]
    if any(item["AllocationId"] != settings["allocation_id"] for item in target_addresses):
        raise ValueError("target has a different EIP; release it through reviewed Terraform first")
    if eip.get("NetworkInterfaceId") == target_eni["NetworkInterfaceId"] and not target_addresses:
        raise ValueError("target EIP association metadata is inconsistent")

    current_id = eip.get("InstanceId")
    current_host = instance(current_id) if current_id else None
    current_eni = primary_interface(current_host) if current_host else None
    marker = active_marker(settings["active_parameter"])
    if marker != "none" and (not current_host or tags(current_host).get("Gala") != marker):
        raise ValueError("active-Gala marker does not match the shared EIP holder")
    if settings["public_group"] in groups(target_eni) and current_id != host["InstanceId"]:
        raise ValueError("inactive target already has public ingress")

    source_commit = command("git", "rev-parse", "HEAD")
    return {
        "version": 1,
        "source_commit": source_commit,
        "target_slug": target_slug,
        "target_instance_id": host["InstanceId"],
        "target_eni": target_eni["NetworkInterfaceId"],
        "target_groups": groups(target_eni),
        "domain": galas[target_slug]["domain"],
        "current_marker": marker,
        "current_instance_id": current_id,
        "current_eni": current_eni["NetworkInterfaceId"] if current_eni else None,
        "current_groups": groups(current_eni) if current_eni else [],
        "eip_allocation_id": settings["allocation_id"],
        "eip_association_id": eip.get("AssociationId"),
        "eip_public_ip": eip["PublicIp"],
        "public_group": settings["public_group"],
        "active_parameter": settings["active_parameter"],
    }


def verify_target_local(plan: dict[str, object]) -> None:
    slug = plan["target_slug"]
    # AWS-RunShellScript invokes /bin/sh. The installed healthcheck itself is
    # Bash and resolves all three domains to this EC2's loopback interface.
    script = (
        f"test -s /var/lib/tibillet-gala/{slug}/releases/deployed-manifest.json && "
        "grep -q -- '--resolve' /usr/local/lib/tibillet-gala/healthcheck.sh && "
        f"/usr/local/lib/tibillet-gala/healthcheck.sh /etc/tibillet-gala/{slug}.conf"
    )
    response = aws(
        "ssm", "send-command", "--document-name", "AWS-RunShellScript",
        "--instance-ids", plan["target_instance_id"],
        "--parameters", json.dumps({"commands": [script]}),
        "--comment", "Read-only local healthcheck before active Gala IP switch",
    )
    command_id = response["Command"]["CommandId"]
    for _ in range(36):
        time.sleep(5)
        try:
            response = aws(
                "ssm", "get-command-invocation", "--command-id", command_id,
                "--instance-id", plan["target_instance_id"],
            )
        except RuntimeError as error:
            if "InvocationDoesNotExist" in str(error):
                continue
            raise
        if response["Status"] == "Success":
            return
        if response["Status"] not in {"Pending", "InProgress", "Delayed"}:
            raise RuntimeError(f"target local healthcheck failed: {response['Status']}")
    raise RuntimeError("target local healthcheck timed out")


def set_groups(interface_id: str, group_ids: list[str]) -> None:
    aws("ec2", "modify-network-interface-attribute", "--network-interface-id", interface_id, "--groups", *sorted(group_ids))


def check_public(plan: dict[str, object]) -> None:
    apex = plan["domain"]
    if not isinstance(apex, str) or not re.fullmatch(r"[a-z0-9.-]+", apex):
        raise ValueError("invalid public domain in switch plan")
    # Leave time within the 15-minute CodeBuild limit for EIP rollback if a
    # certificate or public endpoint never becomes healthy.
    deadline = time.monotonic() + 360
    for host in (apex, f"fedow.{apex}", f"cashless.{apex}"):
        while True:
            result = subprocess.run(
                ["curl", "--silent", "--show-error", "--fail", "--noproxy", "*",
                 "--resolve", f"{host}:443:{plan['eip_public_ip']}",
                 "--max-time", "15", "--output", "/dev/null", f"https://{host}/"],
                capture_output=True, text=True, check=False,
            )
            if result.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"public TLS healthcheck failed for {host}")
            time.sleep(10)


def apply_plan(plan: dict[str, object], settings: dict[str, str]) -> None:
    if plan.get("version") != 1 or not SLUG.fullmatch(str(plan.get("target_slug", ""))):
        raise ValueError("invalid switch plan")
    live = build_plan(plan["target_slug"], settings)
    if live != plan:
        raise ValueError("switch plan is stale; start a new pipeline execution")
    verify_target_local(plan)
    if plan["target_instance_id"] == plan["current_instance_id"] and plan["current_marker"] == plan["target_slug"]:
        print(f"Gala already active: {plan['target_slug']}")
        return

    old_eni = plan["current_eni"]
    target_eni = plan["target_eni"]
    public_group = plan["public_group"]
    try:
        aws("ec2", "associate-address", "--allocation-id", plan["eip_allocation_id"], "--network-interface-id", target_eni, "--allow-reassociation")
        set_groups(target_eni, sorted(set(plan["target_groups"]) | {public_group}))
        if old_eni and old_eni != target_eni:
            set_groups(old_eni, [group for group in plan["current_groups"] if group != public_group])
        if address(plan["eip_allocation_id"]).get("InstanceId") != plan["target_instance_id"]:
            raise RuntimeError("shared EIP did not reach the target instance")
        check_public(plan)
        aws(
            "ssm", "put-parameter", "--name", plan["active_parameter"],
            "--type", "String", "--value", plan["target_slug"], "--overwrite",
        )
    except Exception as error:
        rollback_errors = []
        for operation in (
            lambda: set_groups(target_eni, plan["target_groups"]),
            lambda: set_groups(old_eni, plan["current_groups"]) if old_eni and old_eni != target_eni else None,
            lambda: aws("ec2", "associate-address", "--allocation-id", plan["eip_allocation_id"], "--network-interface-id", old_eni, "--allow-reassociation") if old_eni else None,
        ):
            try:
                operation()
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise RuntimeError(f"switch failed ({error}); rollback incomplete: {'; '.join(rollback_errors)}") from error
        raise RuntimeError(f"switch failed and previous EIP association restored: {error}") from error
    print(f"Active Gala switched to {plan['target_slug']} on {plan['eip_public_ip']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="mode", required=True)
    plan_parser = subcommands.add_parser("plan")
    plan_parser.add_argument("--target", required=True)
    plan_parser.add_argument("--output", required=True, type=Path)
    apply_parser = subcommands.add_parser("apply")
    apply_parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    settings = context()
    if args.mode == "plan":
        result = build_plan(args.target, settings)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"Switch plan: current={result['current_marker']} target={result['target_slug']} "
            f"instance={result['target_instance_id']} EIP={result['eip_public_ip']}"
        )
    else:
        apply_plan(json.loads(args.plan.read_text(encoding="utf-8")), settings)


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
