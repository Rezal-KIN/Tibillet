#!/usr/bin/env python3
"""Create one reproducible Smoke deployment manifest from a Test candidate."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def create(candidate: dict[str, object], pinned: dict[str, object]) -> dict[str, object]:
    if candidate.get("application_repository") != "Rezal-KIN/Tibillet":
        raise ValueError("unexpected candidate repository")
    commit = candidate.get("fork_commit")
    if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
        raise ValueError("candidate must name a complete source commit")
    if candidate.get("platform") != "v1" or pinned.get("schema_version") != 1:
        raise ValueError("unexpected Smoke platform or image-lock schema")
    images = {"lespass_image": candidate.get("lespass_image")}
    images.update({key: pinned.get(key) for key in ("fedow_image", "laboutik_image", "traefik_image")})
    if any(not isinstance(image, str) or not IMAGE.fullmatch(image) for image in images.values()):
        raise ValueError("every Smoke image must be fixed by digest")
    return {
        "release_id": f"smoke-{commit}",
        "gala_slug": "gala-smoke",
        "platform": "v1",
        "application_repository": "Rezal-KIN/Tibillet",
        "fork_commit": commit,
        # The combined repository is also the tested TiBillet source here.
        "tibillet_upstream_commit": commit,
        **images,
        "schema_generation": "v1",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("image_lock", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = create(
        json.loads(args.candidate.read_text(encoding="utf-8")),
        json.loads(args.image_lock.read_text(encoding="utf-8")),
    )
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Smoke manifest created for {manifest['fork_commit']}")


if __name__ == "__main__":
    main()
