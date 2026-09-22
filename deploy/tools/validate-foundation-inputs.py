#!/usr/bin/env python3
"""Validate non-secret CodeBuild inputs for a Paris Gala foundation."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
from pathlib import Path


REGION = "eu-west-3"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
INSTANCE_TYPE = re.compile(r"^t3\.(small|medium|large|xlarge)$")
VPC = re.compile(r"^vpc-[0-9a-f]{8,17}$")
SUBNET = re.compile(r"^subnet-[0-9a-f]{8,17}$")
AMI = re.compile(r"^ami-[0-9a-f]{8,17}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def value(name: str) -> str:
    result = os.environ.get(name, "").strip()
    if not result:
        fail(f"{name} is required")
    return result


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate-foundation-inputs.py OUTPUT_TFVARS.json")

    if value("AWS_DEFAULT_REGION") != REGION:
        fail(f"AWS_DEFAULT_REGION must be {REGION}")

    slug = value("GALA_SLUG")
    if not SLUG.fullmatch(slug) or slug == "bapts":
        fail("GALA_SLUG must be a safe non-Bapts lowercase slug")

    domain = value("GALA_DOMAIN")
    if domain != domain.lower() or not DOMAIN.fullmatch(domain):
        fail("GALA_DOMAIN must be a lowercase public hostname")

    instance_type = value("INSTANCE_TYPE")
    if not INSTANCE_TYPE.fullmatch(instance_type):
        fail("INSTANCE_TYPE must be one of t3.small, t3.medium, t3.large, t3.xlarge")

    try:
        root_volume_size_gib = int(value("ROOT_VOLUME_SIZE_GIB"))
    except ValueError:
        fail("ROOT_VOLUME_SIZE_GIB must be an integer")
    if not 40 <= root_volume_size_gib <= 512:
        fail("ROOT_VOLUME_SIZE_GIB must be between 40 and 512")

    vpc_id = value("VPC_ID")
    subnet_id = value("SUBNET_ID")
    ec2_ami_id = value("EC2_AMI_ID")
    if not VPC.fullmatch(vpc_id):
        fail("VPC_ID is invalid")
    if not SUBNET.fullmatch(subnet_id):
        fail("SUBNET_ID is invalid")
    if not AMI.fullmatch(ec2_ami_id):
        fail("EC2_AMI_ID is invalid")

    source_commit = value("FOUNDATION_SOURCE_COMMIT")
    if not COMMIT.fullmatch(source_commit):
        fail("FOUNDATION_SOURCE_COMMIT must be a full 40-character Git SHA")

    cidrs = []
    for raw_cidr in os.environ.get("SSH_EMERGENCY_CIDRS", "").split(","):
        cidr = raw_cidr.strip()
        if not cidr:
            continue
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            fail(f"SSH_EMERGENCY_CIDRS contains an invalid CIDR: {cidr}")
        if network.prefixlen == 0:
            fail("SSH_EMERGENCY_CIDRS must not allow the whole Internet")
        cidrs.append(str(network))

    output = {
        "aws_region": REGION,
        "environment": "production",
        "gala_account_id": "318629836660",
        "enable_additive_resources": True,
        "enable_backup_storage": True,
        "enable_delivery_platform": True,
        "github_owner": "Rezal-KIN",
        "github_repository": "Tibillet",
        "runtime_repository_ref": source_commit,
        "vpc_id": vpc_id,
        "subnet_id": subnet_id,
        "ec2_ami_id": ec2_ami_id,
        "galas": {
            slug: {
                "platform": "v1",
                "domain": domain,
                "instance_type": instance_type,
                "root_volume_size_gib": root_volume_size_gib,
                "ssh_emergency_cidrs": cidrs,
                "create_instance": True,
                "protect_from_destruction": True,
            }
        },
    }
    Path(sys.argv[1]).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Foundation inputs valid: gala={slug} domain={domain} region={REGION}")


if __name__ == "__main__":
    main()
