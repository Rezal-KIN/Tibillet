#!/usr/bin/env python3
"""Bind a Production manifest to the exact successful Smoke deployment."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


IMAGES = ("lespass_image", "fedow_image", "laboutik_image", "traefik_image")


def compare(manifest: dict[str, object], tested: dict[str, object], slug: str) -> None:
    if manifest.get("gala_slug") != slug or slug == "gala-smoke":
        raise ValueError("Production manifest targets the wrong Gala")
    if manifest.get("platform") != "v1" or tested.get("platform") != "v1":
        raise ValueError("Production release must be a tested v1 stack")
    if manifest.get("fork_commit") != tested.get("fork_commit"):
        raise ValueError("Production commit was not deployed successfully on Smoke")
    for field in IMAGES:
        if manifest.get(field) != tested.get(field):
            raise ValueError(f"{field} differs from the successful Smoke deployment")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--gala", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    # The buildspec consumes exactly two stdout lines: approval summary and
    # MANIFEST_SHA256. Keep the preliminary syntax check from shifting them.
    subprocess.run(
        ["python3", "deploy/tools/runtime/validate-release.py", str(args.manifest)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    commit = manifest["fork_commit"]
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / "tested.json"
        subprocess.run([
            "aws", "s3", "cp", "--only-show-errors",
            f"s3://{args.bucket}/test-validated/smoke-{commit}.json",
            str(marker), "--region", "eu-west-3",
        ], check=True)
        compare(manifest, json.loads(marker.read_text(encoding="utf-8")), args.gala)
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    args.output.write_bytes(args.manifest.read_bytes())
    checksum = hashlib.sha256(args.output.read_bytes()).hexdigest()
    summary = (
        f"manifest_git={source_commit} release={manifest['release_id']} "
        f"gala={args.gala} app_git={commit} "
        + " ".join(f"{name}={manifest[name]}" for name in IMAGES)
        + f" sha256={checksum}"
    )
    if len(summary) > 1000:
        raise ValueError("approval summary exceeds CodePipeline variable limit")
    print(summary)
    print(f"MANIFEST_SHA256={checksum}")


if __name__ == "__main__":
    main()
