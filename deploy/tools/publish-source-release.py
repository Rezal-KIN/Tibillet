#!/usr/bin/env python3
"""Publish a prepared source offer to GitHub, preserving existing asset bytes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


spec = importlib.util.spec_from_file_location("source_offer", Path(__file__).with_name("build-source-offer.py"))
offer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offer)
ASSETS = {"lespass.tar.gz", "fedow.tar.gz", "laboutik.tar.gz", "deployment.tar.gz",
          "source-manifest.json", "SHA256SUMS", "BUILD.md", "LICENSE.txt"}


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True).strip()


def publish(directory: Path) -> str:
    if {p.name for p in directory.iterdir()} != ASSETS or any(not p.is_file() or p.is_symlink() for p in directory.iterdir()):
        raise ValueError("publish only the eight prepared public source assets")
    info = json.loads((directory / "source-manifest.json").read_text())
    commit = info["deployment_commit"]
    if info["application_repository"] != offer.GITHUB_REPOSITORY or not offer.SHA.fullmatch(commit):
        raise ValueError("unexpected source repository or commit")
    release_name = f"{info['release_id']}-{commit[:12]}"
    tag = offer.github_release_tag(release_name)
    for component in list(info["components"].values()) + [info["deployment_archive"]]:
        path = directory / Path(component["archive"]).name
        if hashlib.sha256(path.read_bytes()).hexdigest() != component["sha256"]:
            raise ValueError(f"source archive checksum mismatch: {path.name}")
    repository = offer.GITHUB_REPOSITORY
    if json.loads(gh("repo", "view", repository, "--json", "isPrivate"))["isPrivate"]:
        raise ValueError("source repository must already be public")
    def find_release():
        pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repository}/releases?per_page=100"))
        return next((release for page in pages for release in page if release["tag_name"] == tag), None)
    release = find_release()
    if release is None:
        body = (f"Sources complètes de la version **{info['release_id']}** de TiBillet, "
                "avec les personnalisations AM-Rezal. Téléchargements gratuits, sans connexion, "
                "hébergés sur GitHub indépendamment du serveur du gala.\n\n"
                f"Commit du déploiement : `{commit}`.\n\n"
                "Les quatre archives contiennent Lespass, Fedow modifié, Laboutik modifié et les "
                "scripts de déploiement. Les licences et crédits originaux sont conservés. "
                "Consulter `BUILD.md` pour la reconstruction et `SHA256SUMS` pour les empreintes.\n\n"
                "Les archives automatiques « Source code » de GitHub concernent le dépôt seul ; "
                "les quatre fichiers `.tar.gz` joints constituent l’offre de sources complète.\n")
        with tempfile.TemporaryDirectory() as temporary:
            notes = Path(temporary) / "notes.md"
            notes.write_text(body)
            gh("release", "create", tag, "--repo", repository, "--target", commit, "--draft",
               "--title", f"AM-Rezal — sources {info['release_id']}", "--notes-file", str(notes))
        # The release list can lag immediately after creation. Read the draft
        # by its tag through gh and then fetch its exact ID instead.
        release_id = json.loads(gh("release", "view", tag, "--repo", repository,
                                   "--json", "databaseId"))["databaseId"]
        release = json.loads(gh("api", f"repos/{repository}/releases/{release_id}"))
    if release["draft"]:
        if release["target_commitish"] != commit:
            raise ValueError("draft source release targets a different commit")
    else:
        target = json.loads(gh("api", f"repos/{repository}/git/ref/tags/{tag}"))["object"]
        if target["type"] != "commit" or target["sha"] != commit:
            raise ValueError("existing source release tag targets a different commit")
    assets = {asset["name"]: asset for asset in release["assets"]}
    if set(assets) - ASSETS:
        raise ValueError("existing source release contains unexpected assets")
    missing = []
    for name in sorted(ASSETS):
        path = directory / name
        expected = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if name not in assets:
            if not release["draft"]:
                raise ValueError("published source release is incomplete; do not modify it")
            missing.append(str(path))
        elif assets[name].get("digest") != expected:
            raise ValueError(f"existing source asset has different or unverified bytes: {name}")
    if missing:
        gh("release", "upload", tag, *missing, "--repo", repository)
    uploaded = json.loads(gh("api", f"repos/{repository}/releases/{release['id']}"))
    digests = {asset["name"]: asset.get("digest") for asset in uploaded["assets"]}
    for name in ASSETS:
        if digests.get(name) != "sha256:" + hashlib.sha256((directory / name).read_bytes()).hexdigest():
            raise ValueError(f"uploaded source asset not verified: {name}")
    if uploaded["draft"]:
        gh("release", "edit", tag, "--repo", repository, "--draft=false")
    offer.verify_github_release(directory, release_name)
    return f"https://github.com/{repository}/releases/tag/{tag}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="prepared release directory containing exactly eight assets")
    args = parser.parse_args()
    print(publish(args.directory))


if __name__ == "__main__":
    main()
