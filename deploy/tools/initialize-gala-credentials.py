#!/usr/bin/env python3
"""Create the first generated-credential version for each Gala, exactly once.

Foundation runs this after Terraform has created the secret containers. No
generated value is written to Terraform state, a pipeline artifact, or logs.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ACCOUNT = "318629836660"
REGION = "eu-west-3"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
PROJECT = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def aws(*arguments: str) -> str:
    result = subprocess.run(
        ["aws", *arguments, "--region", REGION],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"AWS {arguments[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def generated_payload() -> dict[str, str | int]:
    def fernet_key() -> str:
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")

    return {
        "schema_version": 1,
        "fedow_secret_key": secrets.token_hex(25),
        "fedow_fernet_key": fernet_key(),
        "fedow_postgres_password": secrets.token_urlsafe(36),
        "laboutik_django_secret": secrets.token_hex(25),
        "laboutik_fernet_key": fernet_key(),
        "laboutik_postgres_password": secrets.token_urlsafe(36),
        "lespass_django_secret": secrets.token_hex(25),
        "lespass_fernet_key": fernet_key(),
        "lespass_postgres_password": secrets.token_urlsafe(36),
        "active_gala_api_token": secrets.token_hex(32),
    }


def current_version_exists(secret_id: str) -> bool:
    versions = json.loads(
        aws(
            "secretsmanager", "describe-secret", "--secret-id", secret_id,
            "--query", "VersionIdsToStages", "--output", "json",
        )
    )
    if versions is None:
        return False
    if not isinstance(versions, dict):
        raise RuntimeError(f"unexpected version metadata for {secret_id}")
    if any("AWSCURRENT" in stages for stages in versions.values()):
        return True
    if versions:
        raise RuntimeError(f"{secret_id} has versions but no AWSCURRENT; manual inspection required")
    return False


def initialize(secret_id: str, slug: str) -> None:
    if current_version_exists(secret_id):
        print(f"Generated credentials preserved: {slug}")
        return

    # A stable client token makes concurrent/retried Foundation finalizers
    # unable to replace the first successfully written version.
    token = hashlib.sha256(f"tibillet-gala-generated-v1:{secret_id}".encode()).hexdigest()
    descriptor, filename = tempfile.mkstemp(prefix="gala-generated-", suffix=".json")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            json.dump(generated_payload(), destination, separators=(",", ":"))
        os.chmod(filename, 0o600)
        for attempt in range(5):
            try:
                aws(
                    "secretsmanager", "put-secret-value", "--secret-id", secret_id,
                    "--client-request-token", token,
                    "--secret-string", f"file://{filename}",
                    "--query", "VersionId", "--output", "text",
                )
                break
            except RuntimeError as error:
                if "ResourceExistsException" in str(error) and current_version_exists(secret_id):
                    break
                if "AccessDeniedException" not in str(error) or attempt == 4:
                    raise
                time.sleep(3)
        if not current_version_exists(secret_id):
            raise RuntimeError(f"generated secret has no AWSCURRENT version: {slug}")
        print(f"Generated credentials initialized: {slug}")
    finally:
        Path(filename).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--project-name", required=True)
    args = parser.parse_args()

    if not PROJECT.fullmatch(args.project_name):
        raise SystemExit("invalid project name")
    if os.environ.get("AWS_DEFAULT_REGION") != REGION:
        raise SystemExit(f"AWS_DEFAULT_REGION must be {REGION}")
    if aws("sts", "get-caller-identity", "--query", "Account", "--output", "text") != ACCOUNT:
        raise SystemExit("wrong AWS account for Gala secret initialization")
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    if catalog.get("version") != 1 or not isinstance(catalog.get("galas"), dict):
        raise SystemExit("invalid Foundation catalog")

    for slug in sorted(catalog["galas"]):
        if not SLUG.fullmatch(slug) or slug == "bapts":
            raise SystemExit("invalid Gala slug in Foundation catalog")
        initialize(f"{args.project_name}/galas/{slug}/generated", slug)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
