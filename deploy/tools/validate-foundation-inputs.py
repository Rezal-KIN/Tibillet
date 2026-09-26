#!/usr/bin/env python3
"""Validate non-secret CodePipeline inputs and extend the Gala catalog safely."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path


REGION = "eu-west-3"
SHARED_DOMAIN = "galas-am-aix.rezal.fr"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
INSTANCE_TYPE = re.compile(r"^t3\.(small|medium|large|xlarge)$")
VPC = re.compile(r"^vpc-[0-9a-f]{8,17}$")
SUBNET = re.compile(r"^subnet-[0-9a-f]{8,17}$")
AMI = re.compile(r"^ami-[0-9a-f]{8,17}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
CONNECTION = re.compile(r"^arn:aws:codeconnections:eu-west-3:318629836660:connection/[0-9a-f-]{36}$")
RETIRE_SMOKE_PIPELINE_REQUEST = "Retire Smoke Production Pipeline"
PREPARE_VALIDATION_RETIREMENT_REQUEST = "Prepare Validation Retirement"
RETIRE_VALIDATION_INSTANCES_REQUEST = "Retire Validation Instances"
VALIDATION_SLUGS = ("gala-validation", "gala-validation-2")


def validation_retirement_phase(name: str) -> str | None:
    if name == PREPARE_VALIDATION_RETIREMENT_REQUEST:
        return "prepare"
    if name == RETIRE_VALIDATION_INSTANCES_REQUEST:
        return "retire"
    return None


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def value(name: str) -> str:
    result = os.environ.get(name, "").strip()
    if not result:
        fail(f"{name} is required")
    return result


def gala_slug(name: str) -> str:
    if name == RETIRE_SMOKE_PIPELINE_REQUEST:
        return "gala-smoke"
    if validation_retirement_phase(name):
        return "gala-validation"
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    if not SLUG.fullmatch(slug) or slug in {"bapts", "gala-smoke"}:
        fail("GALA_NAME must produce a safe, unique non-Smoke Gala identifier")
    return slug


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

    gala_name = value("GALA_NAME")
    slug = gala_slug(gala_name)
    retire_smoke_pipeline = gala_name == RETIRE_SMOKE_PIPELINE_REQUEST
    validation_retirement = validation_retirement_phase(gala_name)
    domain = value("SHARED_GALA_DOMAIN")
    if domain != domain.lower() or not DOMAIN.fullmatch(domain):
        fail("SHARED_GALA_DOMAIN must be a lowercase public hostname")
    if domain != SHARED_DOMAIN:
        fail("SHARED_GALA_DOMAIN must equal the approved shared public domain")

    instance_type = value("FOUNDATION_INSTANCE_TYPE")
    if not INSTANCE_TYPE.fullmatch(instance_type):
        fail("FOUNDATION_INSTANCE_TYPE must be one of t3.small, t3.medium, t3.large, t3.xlarge")

    try:
        root_volume_size_gib = int(value("FOUNDATION_ROOT_VOLUME_SIZE_GIB"))
    except ValueError:
        fail("FOUNDATION_ROOT_VOLUME_SIZE_GIB must be an integer")
    if not 40 <= root_volume_size_gib <= 512:
        fail("FOUNDATION_ROOT_VOLUME_SIZE_GIB must be between 40 and 512")

    catalog = read_catalog(args.catalog)
    vpc_id, subnet_id, ec2_ami_id = (catalog.get(field) for field in ("vpc_id", "subnet_id", "ec2_ami_id"))
    if not isinstance(vpc_id, str) or not VPC.fullmatch(vpc_id):
        fail("catalog vpc_id is missing or invalid")
    if not isinstance(subnet_id, str) or not SUBNET.fullmatch(subnet_id):
        fail("catalog subnet_id is missing or invalid")
    if not isinstance(ec2_ami_id, str) or not AMI.fullmatch(ec2_ami_id):
        fail("catalog ec2_ami_id is missing or invalid")

    github_connection_arn = value("GITHUB_CONNECTION_ARN")
    if not CONNECTION.fullmatch(github_connection_arn):
        fail("GITHUB_CONNECTION_ARN must be an approved Paris CodeConnections ARN")

    source_commit = value("FOUNDATION_SOURCE_COMMIT")
    if not COMMIT.fullmatch(source_commit):
        fail("FOUNDATION_SOURCE_COMMIT must be a full 40-character Git SHA")

    cidrs = []
    galas = catalog["galas"]
    assert isinstance(galas, dict)
    if slug in galas and not isinstance(galas[slug], dict):
        fail(f"invalid catalog entry for {slug}")

    for existing_slug, existing in galas.items():
        if not isinstance(existing, dict):
            fail(f"invalid catalog entry for {existing_slug}")
        historical_smoke = existing_slug == "gala-smoke" and existing.get("domain") == "smoke.galas-am-aix.rezal.fr"
        if existing.get("domain") != SHARED_DOMAIN and not historical_smoke:
            fail(f"unexpected public domain for {existing_slug}; review the catalog before adding a Gala")
        if historical_smoke:
            # The reviewed one-IP migration makes Smoke use the same public
            # hostnames. No existing EC2 is replaced: user_data is ignored.
            existing["domain"] = SHARED_DOMAIN

    # The two exact moved blocks require their old protected count to be zero.
    # Until Prepare has committed the catalogue, refuse every other operation
    # before planning; this prevents an accidental replacement during retry.
    if not validation_retirement:
        for validation_slug in VALIDATION_SLUGS:
            existing = galas.get(validation_slug)
            if existing and existing.get("create_instance") is True and existing.get("protect_from_destruction") is not False:
                fail("run Prepare Validation Retirement before other Foundation operations")

    new_gala = {
        "platform": "v1",
        "domain": domain,
        "instance_type": instance_type,
        "root_volume_size_gib": root_volume_size_gib,
        "ssh_emergency_cidrs": cidrs,
        # An ephemeral outbound IP is assigned at launch; only the active
        # Gala receives the separately managed shared public EIP.
        "associate_public_ip_address": True,
        "create_instance": True,
        "protect_from_destruction": True,
    }
    if validation_retirement:
        for validation_slug in VALIDATION_SLUGS:
            existing = galas.get(validation_slug)
            if not isinstance(existing, dict):
                fail(f"missing historical validation Gala {validation_slug}")
            if validation_retirement == "prepare":
                if existing.get("create_instance") is not True:
                    fail(f"{validation_slug} has no EC2 to prepare for retirement")
                existing["protect_from_destruction"] = False
            else:
                if existing.get("protect_from_destruction") is not False:
                    fail(f"prepare {validation_slug} before terminating its EC2")
                existing["create_instance"] = False
    elif retire_smoke_pipeline:
        if slug not in galas or galas[slug].get("create_instance") is not True:
            fail("Smoke pipeline retirement requires an existing Terraform-managed Smoke EC2")
    elif slug in galas:
        if galas[slug] != new_gala:
            fail(f"existing Gala {slug} differs from the permanent configuration; use a reviewed migration")
    else:
        galas[slug] = new_gala

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
    print(f"Foundation inputs valid: operation={slug} total_galas={len(galas)} region={REGION}")


if __name__ == "__main__":
    main()
