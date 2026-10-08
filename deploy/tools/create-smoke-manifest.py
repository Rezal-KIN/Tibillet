#!/usr/bin/env python3
"""Create one reproducible Smoke deployment manifest from a Test candidate."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from card_stock import EMPTY_STOCK, validate_catalogue, smoke_release_id
from application_images import validate_image_builds

IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def create(candidate: dict[str, object], pinned: dict[str, object], stock=None) -> dict[str, object]:
    if candidate.get("application_repository") != "Rezal-KIN/Tibillet":
        raise ValueError("unexpected candidate repository")
    commit = candidate.get("fork_commit")
    if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
        raise ValueError("candidate must name a complete source commit")
    if candidate.get("platform") != "v1" or pinned.get("schema_version") != 1:
        raise ValueError("unexpected Smoke platform or image-lock schema")
    images = {"lespass_image": candidate.get("lespass_image")}
    builds = validate_image_builds(candidate)
    images.update({key: candidate.get(key) if builds else pinned.get(key)
                   for key in ("fedow_image", "laboutik_image")})
    images['traefik_image'] = pinned.get('traefik_image')
    if any(not isinstance(image, str) or not IMAGE.fullmatch(image) for image in images.values()):
        raise ValueError("every Smoke image must be fixed by digest")
    stock = validate_catalogue(EMPTY_STOCK if stock is None else stock)
    manifest = {
        "release_id": smoke_release_id(commit, stock),
        "gala_slug": "gala-smoke",
        "platform": "v1",
        "application_repository": "Rezal-KIN/Tibillet",
        "fork_commit": commit,
        # The combined repository is also the tested TiBillet source here.
        "tibillet_upstream_commit": commit,
        **images,
        "schema_generation": "v1",
        "card_stock": stock,
    }
    if builds:
        manifest['image_builds'] = builds
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("image_lock", type=Path)
    parser.add_argument("output", type=Path)
    # Existing CodeBuild projects embed their buildspec in Terraform. Keep
    # their previous CLI invocation working, while still reading this commit's
    # versioned catalogue (never a mutable S3 selector).
    parser.add_argument("--card-stock", type=Path,
                        default=Path(__file__).resolve().parents[1] / 'card-stock.json')
    args = parser.parse_args()
    manifest = create(
        json.loads(args.candidate.read_text(encoding="utf-8")),
        json.loads(args.image_lock.read_text(encoding="utf-8")),
        json.loads(args.card_stock.read_text(encoding="utf-8")),
    )
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Smoke manifest created for {manifest['fork_commit']}")


if __name__ == "__main__":
    main()
