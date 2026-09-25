#!/usr/bin/env python3
"""One-time migration: restore outbound IP on an inactive legacy Gala host.

Older EC2s launched while their own EIP was attached may not obtain an
automatic public IPv4 when that EIP is released. This operation never edits
the guest: it restarts only the exact inactive Terraform-managed instance and
verifies that the subnet gives it a temporary public IP and SSM connectivity.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time


ACCOUNT = "318629836660"
REGION = "eu-west-3"
PROJECT = "tibillet-gala-paris"


def aws(*args: str) -> dict[str, object]:
    result = subprocess.run(["aws", *args, "--region", REGION, "--output", "json"],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def host(instance_id: str) -> dict[str, object]:
    response = aws("ec2", "describe-instances", "--instance-ids", instance_id)
    instances = [instance for reservation in response["Reservations"] for instance in reservation["Instances"]]
    if len(instances) != 1:
        raise ValueError("expected one EC2 instance")
    return instances[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--gala", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"i-[0-9a-f]{8,17}", args.instance_id):
        raise ValueError("invalid instance ID")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", args.gala):
        raise ValueError("invalid Gala slug")
    if aws("sts", "get-caller-identity")["Account"] != ACCOUNT:
        raise ValueError("wrong AWS account")
    marker = aws("ssm", "get-parameter", "--name", f"/{PROJECT}/active-gala")["Parameter"]["Value"]
    if marker == args.gala:
        raise ValueError("refusing to restart the active Gala")
    instance = host(args.instance_id)
    tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}
    if tags.get("Project") != PROJECT or tags.get("Gala") != args.gala or tags.get("ManagedBy") != "terraform":
        raise ValueError("instance is not the requested Terraform Gala")
    if len(instance["NetworkInterfaces"]) != 1 or instance["NetworkInterfaces"][0]["Attachment"]["DeviceIndex"] != 0:
        raise ValueError("instance must have exactly one primary network interface")
    if instance["State"]["Name"] != "running":
        raise ValueError("instance must be running before migration")
    if instance.get("PublicIpAddress"):
        print(f"Gala already has outbound public IPv4: {args.gala}")
        return
    addresses = aws("ec2", "describe-addresses", "--filters", f"Name=instance-id,Values={args.instance_id}")["Addresses"]
    if addresses:
        raise ValueError("instance still holds an EIP")
    print(f"Restarting inactive legacy Gala {args.gala} to restore temporary outbound IPv4", flush=True)
    aws("ec2", "stop-instances", "--instance-ids", args.instance_id)
    subprocess.run(["aws", "ec2", "wait", "instance-stopped", "--instance-ids", args.instance_id, "--region", REGION], check=True)
    aws("ec2", "start-instances", "--instance-ids", args.instance_id)
    subprocess.run(["aws", "ec2", "wait", "instance-running", "--instance-ids", args.instance_id, "--region", REGION], check=True)
    for _ in range(36):
        instance = host(args.instance_id)
        online = aws("ssm", "describe-instance-information", "--filters", f"Key=InstanceIds,Values={args.instance_id}")["InstanceInformationList"]
        if instance.get("PublicIpAddress") and len(online) == 1 and online[0]["PingStatus"] == "Online":
            print(f"Outbound IPv4 and SSM restored for {args.gala}")
            return
        time.sleep(10)
    raise RuntimeError("instance restarted but public IPv4 or SSM did not recover")


if __name__ == "__main__":
    main()
