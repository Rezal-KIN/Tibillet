#!/usr/bin/env python3
"""Initialize stable Gala entries inside the two environment secrets.

Existing entries are never regenerated. Compare-and-swap of AWSCURRENT
keeps concurrent finalizers from overwriting another Gala entry.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
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
        raise RuntimeError(f"AWS {arguments[0]} {arguments[1]} failed")
    return result.stdout.strip()


def generated_payload() -> dict[str, str | int]:
    def fernet_key() -> str:
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")

    return {
        "schema_version": 1,
        "fedow_secret_key": secrets.token_hex(25),
        "fedow_fernet_key": fernet_key(),
        "laboutik_django_secret": secrets.token_hex(25),
        "laboutik_fernet_key": fernet_key(),
        "laboutik_postgres_password": secrets.token_urlsafe(36),
        "lespass_django_secret": secrets.token_hex(25),
        "lespass_fernet_key": fernet_key(),
        "lespass_postgres_password": secrets.token_urlsafe(36),
        "active_gala_api_token": secrets.token_hex(32),
    }


def read_environment(secret_id: str) -> tuple[dict, str]:
    response = json.loads(aws("secretsmanager", "get-secret-value", "--secret-id", secret_id, "--output", "json"))
    payload = json.loads(response["SecretString"])
    if (not isinstance(payload, dict) or payload.get("schema_version") != 2
            or payload.get("environment") not in {"dev", "prod"}
            or not isinstance(payload.get("galas"), dict)):
        raise RuntimeError("environment secret must be populated before Foundation initializes Gala keys")
    return payload, response["VersionId"]


def publish_environment(secret_id: str, prior_version: str, payload: dict) -> bool:
    encoded = json.dumps(payload, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 65536:
        raise RuntimeError("environment secret exceeds the AWS size limit")
    token = str(uuid.uuid4())
    pending = "GALA_INIT_" + token
    descriptor, filename = tempfile.mkstemp(prefix="gala-environment-", suffix=".json")
    written = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(encoded)
        os.chmod(filename, 0o600)
        aws("secretsmanager", "put-secret-value", "--secret-id", secret_id,
            "--client-request-token", token, "--version-stages", pending,
            "--secret-string", f"file://{filename}", "--query", "VersionId", "--output", "text")
        written = True
        try:
            aws("secretsmanager", "update-secret-version-stage", "--secret-id", secret_id,
                "--version-stage", "AWSCURRENT", "--remove-from-version-id", prior_version,
                "--move-to-version-id", token)
        except RuntimeError:
            current, version = read_environment(secret_id)
            if version == token:
                return True
            if version != prior_version:
                return False
            raise
        return True
    finally:
        Path(filename).unlink(missing_ok=True)
        if written:
            aws("secretsmanager", "update-secret-version-stage", "--secret-id", secret_id,
                "--version-stage", pending, "--remove-from-version-id", token)


def initialize(secret_id: str, slug: str) -> None:
    expected_environment = "dev" if slug in {"gala-smoke", "gala-smoke-cawl"} else "prod"
    for _ in range(5):
        payload, version = read_environment(secret_id)
        if payload["environment"] != expected_environment:
            raise RuntimeError("Gala keys target the wrong environment")
        if slug in payload["galas"]:
            if not isinstance(payload["galas"][slug], dict) or payload["galas"][slug].get("schema_version") != 1:
                raise RuntimeError("existing Gala keys have an invalid schema")
            print(f"Generated credentials preserved: {slug}")
            return
        payload["galas"][slug] = generated_payload()
        if publish_environment(secret_id, version, payload):
            print(f"Generated credentials initialized: {slug}")
            return
    raise RuntimeError("environment secret changed repeatedly; retry Foundation finalization")


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
        mode = "test" if slug in {"gala-smoke", "gala-smoke-cawl"} else "live"
        initialize(f"{args.project_name}/shared/integrations-stripe-{mode}", slug)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
