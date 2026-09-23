#!/usr/bin/env python3
"""Validate non-secret CodePipeline inputs and extend the Gala catalog safely."""
from __future__ import annotations

import argparse
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
CONNECTION = re.compile(r"^arn:aws:codeconnections:eu-west-3:318629836660:connection/[0-9a-f-]{36}$")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def value(name: str) -> str:
    result = os.environ.get(name, "").strip()
    if not result:
        fail(f"{name} is required")
    return result


def read_catalog(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": 1, "galas": {}}
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"foundation catalog is not valid JSON: {error.msg}")
    if not isinstance(catalog, dict) or catalog.get("version") != 1 or not isinstance(catalog.get("galas"), dict):
        fail("foundation catalog must contain version=1 and a galas object")
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_tfvars", type=Path)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--catalog-output", type=Path, required=True)
    args = parser.parse_args()

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

    vpc_id, subnet_id, ec2_ami_id = value("VPC_ID"), value("SUBNET_ID"), value("EC2_AMI_ID")
    if not VPC.fullmatch(vpc_id):
        fail("VPC_ID is invalid")
    if not SUBNET.fullmatch(subnet_id):
        fail("SUBNET_ID is invalid")
    if not AMI.fullmatch(ec2_ami_id):
        fail("EC2_AMI_ID is invalid")

    github_connection_arn = value("GITHUB_CONNECTION_ARN")
    if not CONNECTION.fullmatch(github_connection_arn):
        fail("GITHUB_CONNECTION_ARN must be an approved Paris CodeConnections ARN")

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

    catalog = read_catalog(args.catalog)
    galas = catalog["galas"]
    assert isinstance(galas, dict)
    if slug in galas:
        fail(f"GALA_SLUG {slug} already exists in the foundation catalog; use a reviewed Terraform change for an existing Gala")

    for field, provided in (("vpc_id", vpc_id), ("subnet_id", subnet_id), ("ec2_ami_id", ec2_ami_id)):
        existing = catalog.get(field)
        if existing is not None and existing != provided:
            fail(f"{field} must match the existing foundation catalog")
        catalog[field] = provided

    galas[slug] = {
        "platform": "v1",
        "domain": domain,
        "instance_type": instance_type,
        "root_volume_size_gib": root_volume_size_gib,
        "ssh_emergency_cidrs": cidrs,
        "create_instance": True,
        "protect_from_destruction": True,
    }

    foundation_role = value("FOUNDATION_CODEBUILD_ROLE_ARN")
    state_bucket = value("TERRAFORM_STATE_BUCKET")
    state_key = value("TERRAFORM_STATE_KEY")
    manage_foundation_role = value("MANAGE_FOUNDATION_CODEBUILD_ROLE")
    if manage_foundation_role not in {"true", "false"}:
        fail("MANAGE_FOUNDATION_CODEBUILD_ROLE must be true or false")
    output = {
        "aws_region": REGION,
        "environment": "production",
        "gala_account_id": "318629836660",
        "enable_additive_resources": True,
        "enable_backup_storage": True,
        "enable_delivery_platform": True,
        "enable_production_pipeline": True,
        "enable_foundation_pipeline": True,
        "foundation_codebuild_role_arn": foundation_role,
        "manage_foundation_codebuild_role": manage_foundation_role == "true",
        "terraform_state_bucket_name": state_bucket,
        "terraform_state_key": state_key,
        "github_connection_arn": github_connection_arn,
        "github_owner": "Rezal-KIN",
        "github_repository": "Tibillet",
        "runtime_repository_ref": source_commit,
        "vpc_id": catalog["vpc_id"],
        "subnet_id": catalog["subnet_id"],
        "ec2_ami_id": catalog["ec2_ami_id"],
        "galas": galas,
    }
    args.catalog_output.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_tfvars.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Foundation inputs valid: new_gala={slug} total_galas={len(galas)} region={REGION}")


if __name__ == "__main__":
    main()
