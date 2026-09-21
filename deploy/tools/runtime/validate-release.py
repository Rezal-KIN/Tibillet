#!/usr/bin/env python3
"""Validate a non-secret Gala release manifest before deployment."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PLATFORMS = {"v1", "v2-preview", "v2"}
SHA256_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
SHA = re.compile(r"^[0-9a-f]{7,64}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
REQUIRED = {
    "release_id",
    "gala_slug",
    "platform",
    "application_repository",
    "fork_commit",
    "tibillet_upstream_commit",
    "lespass_image",
    "fedow_image",
    "laboutik_image",
    "traefik_image",
    "schema_generation",
}
APPLICATION_REPOSITORY = "Rezal-KIN/Tibillet"
IMMUTABLE_IMAGES = ("lespass_image", "fedow_image", "laboutik_image", "traefik_image")


def reject(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        reject("usage: validate-release.py RELEASE_MANIFEST.json")
    path = Path(sys.argv[1])
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        reject(f"cannot read release manifest: {exc}")
    if not isinstance(document, dict):
        reject("release manifest must be a JSON object")
    missing = REQUIRED.difference(document)
    if missing:
        reject("missing required release fields: " + ", ".join(sorted(missing)))
    if not SLUG.fullmatch(str(document["gala_slug"])):
        reject("gala_slug is invalid")
    if document["platform"] not in PLATFORMS:
        reject("platform must be v1, v2-preview, or v2")
    if not SHA.fullmatch(str(document["fork_commit"])):
        reject("fork_commit must be a fixed hexadecimal Git SHA")
    if document["application_repository"] != APPLICATION_REPOSITORY:
        reject(f"application_repository must be {APPLICATION_REPOSITORY}")
    if not SHA.fullmatch(str(document["tibillet_upstream_commit"])):
        reject("tibillet_upstream_commit must be a fixed hexadecimal Git SHA")
    for field in IMMUTABLE_IMAGES:
        if not SHA256_IMAGE.fullmatch(str(document[field])):
            reject(f"{field} must be an immutable image digest reference")
    forbidden_fields = {
        "account_id",
        "action",
        "backup",
        "dns",
        "instance_id",
        "preview",
        "region",
        "secret_arn",
    }
    present_forbidden_fields = forbidden_fields.intersection(document)
    if present_forbidden_fields:
        reject("release manifests must not contain deployment scope or secret fields: " + ", ".join(sorted(present_forbidden_fields)))
    print(f"Release manifest valid: {document['release_id']}")


if __name__ == "__main__":
    main()
