#!/usr/bin/env python3
"""Build an AGPL source offer from fixed Git revisions, never a live directory.

Rezal-KIN modifications, 2026-10-03. Licensed under AGPL-3.0; see LICENSE.
Only public Git content is read. Containers, dotenvs and databases are not read.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath


SHA = re.compile(r"^[0-9a-f]{40}$")
RELEASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REPOSITORIES = {"TiBillet/Fedow", "TiBillet/LaBoutik"}
PRIVATE_DIRS = {".git", ".context", ".venv", "node_modules", "__pycache__",
                "database", "logs", "backup", "Backup", "certs", "ssh"}
NOTICE = """TiBillet was created by its upstream authors, including Cooperative Code Commun.
Original copyright, license and attribution notices are retained in these sources.
Rezal-KIN maintains a modified Gala deployment. Modifications imported into the
public fork on 2026-09-21; source-offer changes prepared on 2026-10-03.
The modified applications are distributed under GNU AGPL version 3 (see LICENSE).
Third-party components retain their respective licenses and notices.
No warranty is provided, to the extent permitted by applicable law.
"""


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def revision(repo: Path, ref: str) -> str:
    if ref != "HEAD" and not SHA.fullmatch(ref):
        raise ValueError("source revisions must be full Git commit hashes")
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()


def safe_source(path: str) -> bool:
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ValueError("unsafe source archive path")
    # This versioned calibration curve is read by Fedow's dashboard. It is a
    # source resource in the public upstream snapshot, not a database dump.
    if path == "database/courbe_survie.json":
        return True
    if any(part in PRIVATE_DIRS - {"backup", "Backup", "database", "logs"} for part in p.parts):
        return False
    if any(part in {"backup", "Backup", "database", "logs", "www"} for part in p.parts):
        # Preserve versioned backup programs and empty-directory markers needed
        # by upstream Dockerfiles, never dumps, media or logs.
        return p.suffix in {".sh", ".py"} or p.name in {"__init__", ".gitkeep", ".gitignore"}
    # Runtime/media output is not source. Source assets live in static/.
    if "www" in p.parts:
        return False
    name = p.name.lower()
    if name == ".env.example":
        return True
    if name.startswith((".env", "env_", "env.")) or name in {"env", "env_example", "env_test2"}:
        return False
    return not (name.endswith((".pem", ".key", ".p12", ".sqlite3", ".sql", ".pyc", ".log"))
                or name.startswith("acme.json"))


def read_archive(data: bytes, strip_root: bool = False) -> dict[str, tuple[bytes, int]]:
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        roots = {PurePosixPath(m.name).parts[0] for m in archive.getmembers() if m.name}
        if strip_root and len(roots) != 1:
            raise ValueError("upstream archive must contain a single repository root")
        for member in archive:
            name = member.name.partition("/")[2] if strip_root else member.name
            if not name or member.isdir():
                continue
            if not safe_source(name):
                continue
            if not member.isfile():
                raise ValueError(f"unsupported source archive member: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("unreadable source archive member")
            files[name] = (stream.read(), 0o755 if member.mode & 0o111 else 0o644)
    return files


def snapshot(repo: Path, commit: str) -> dict[str, tuple[bytes, int]]:
    return read_archive(git(repo, "archive", "--format=tar", commit))


def deployment_overlays(component: str, deployment: dict) -> dict[str, str]:
    """Read the code bind mounts of the pinned public Compose file.

    Directory mounts are runtime data. Every mounted .py/.html file must be
    present in the Git snapshot; an absent source stops publication.
    """
    folder = "Fedow" if component == "fedow" else "Laboutik"
    root = "/home/fedow/Fedow/" if component == "fedow" else "/DjangoFiles/"
    compose = deployment[f"deploy/{folder}/docker-compose.yml"][0].decode()
    overlays = {}
    for origin, target in re.findall(r"^\s*-\s+(\.\.?/[^:\s]+):([^:\s]+)", compose, re.MULTILINE):
        origin = origin.removeprefix("./")
        if origin == "../source/admin-templates" and target == root.rstrip("/") + "/source_templates":
            prefix = "deploy/source/admin-templates/"
            for name in deployment:
                if name.startswith(prefix):
                    overlays[name] = "source_templates/" + name[len(prefix):]
            continue
        if target.startswith(root) and PurePosixPath(target).suffix in {".py", ".html", ".js", ".mjs", ".css"}:
            overlays[f"deploy/{folder}/{origin}"] = target[len(root):]
    return overlays


def verify_working_tree(repo: Path, commit: str) -> None:
    """Fail if code/config to be mounted differs from its public Git snapshot."""
    deployment = snapshot(repo, commit)
    for name, (expected, _) in deployment.items():
        if name.startswith("deploy/") and PurePosixPath(name).suffix in {".py", ".html", ".yml", ".conf", ".sh"}:
            if (repo / name).read_bytes() != expected:
                raise ValueError(f"deployment source differs from its Git revision: {name}")
    prefix = "deploy/source/admin-templates/"
    for path in (repo / prefix).rglob("*"):
        if path.is_file() and str(path.relative_to(repo)) not in deployment:
            raise ValueError("unversioned file in the mounted admin templates")


def upstream_source(spec: dict, cache: Path) -> dict[str, tuple[bytes, int]]:
    repository, commit = spec["repository"], spec["commit"]
    if repository not in REPOSITORIES or not SHA.fullmatch(commit):
        raise ValueError("unsupported upstream repository or revision")
    expected = spec["archive_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("upstream archive must have a recorded SHA-256")
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{repository.replace('/', '-')}-{commit}.tar.gz"
    if path.exists():
        data = path.read_bytes()
    else:
        url = f"https://codeload.github.com/{repository}/tar.gz/{commit}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(128 * 1024 * 1024 + 1)
        if len(data) > 128 * 1024 * 1024:
            raise ValueError("upstream source archive too large")
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"upstream source archive checksum mismatch: {repository}")
    if not path.exists():
        path.write_bytes(data)
    return read_archive(data, strip_root=True)


def write_archive(path: Path, files: dict[str, tuple[bytes, int]]) -> str:
    # Fixed timestamps produce stable archives and checksums on retries.
    with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, (data, mode) in sorted(files.items()):
                member = tarfile.TarInfo(f"source/{name}")
                member.size, member.mode = len(data), mode
                archive.addfile(member, io.BytesIO(data))
    path.chmod(0o644)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(repo: Path, manifest: dict, catalog: dict, output: Path, cache: Path,
          deployment_commit: str = "HEAD", index_output: Path | None = None) -> dict:
    if manifest.get("application_repository") != "Rezal-KIN/Tibillet":
        raise ValueError("source offer must target the public Rezal fork")
    if not RELEASE.fullmatch(str(manifest.get("release_id", ""))):
        raise ValueError("invalid source release name")
    for component in ("lespass", "fedow", "laboutik"):
        if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", str(manifest.get(f"{component}_image", ""))):
            raise ValueError("source offer requires immutable image digests")
    app_commit = revision(repo, manifest["fork_commit"])
    deploy_commit = revision(repo, deployment_commit)
    deployment = snapshot(repo, deploy_commit)
    application = snapshot(repo, app_commit)
    release_name = f"{manifest['release_id']}-{deploy_commit[:12]}"
    release_root = output / "releases" / release_name
    release_root.parent.mkdir(parents=True, exist_ok=True)
    output.chmod(0o755)
    release_root.parent.chmod(0o755)
    build_guide = (Path(__file__).resolve().parents[1] / "source" / "BUILD.md").read_bytes()
    source_info = {
        "schema_version": 1, "release_id": manifest["release_id"],
        "application_repository": "Rezal-KIN/Tibillet", "deployment_commit": deploy_commit,
        "license": "AGPL-3.0", "components": {},
    }
    with tempfile.TemporaryDirectory(dir=release_root.parent, prefix=".source-build-") as tmp:
        stage = Path(tmp)
        for component in ("lespass", "fedow", "laboutik"):
            overlays = {}
            if component == "lespass":
                files = dict(application)
                base_repository, base_commit = "Rezal-KIN/Tibillet", app_commit
            else:
                spec = catalog[component]
                if spec["image"] != manifest[f"{component}_image"]:
                    raise ValueError(f"source revision not audited for {component} image digest")
                files = upstream_source(spec, cache)
                base_repository, base_commit = spec["repository"], spec["commit"]
                for target, patch in spec.get("image_overlays", {}).items():
                    if not safe_source(target):
                        raise ValueError("private file cannot be an image source override")
                    content, mode = files[target]
                    if hashlib.sha256(content).hexdigest() != patch["original_sha256"]:
                        raise ValueError("image source override does not match the audited original")
                    for old, new in patch["replacements"]:
                        if content.count(old.encode()) != 1:
                            raise ValueError("image source override is ambiguous")
                        content = content.replace(old.encode(), new.encode())
                    files[target] = content, mode
                    overlays[target] = {"source": "audited image build change", "sha256": hashlib.sha256(content).hexdigest()}
                for origin, target in deployment_overlays(component, deployment).items():
                    if not safe_source(origin) or not safe_source(target):
                        raise ValueError("private file cannot be a source overlay")
                    files[target] = deployment[origin]
                    overlays[target] = {"source": origin, "sha256": hashlib.sha256(files[target][0]).hexdigest()}
                # Supply non-secret environment examples from the public deployment.
                folder = "Fedow" if component == "fedow" else "Laboutik"
                files[".env.example"] = deployment[f"deploy/{folder}/.env.example"]
            files.setdefault("LICENSE", deployment["LICENSE"])
            files["REZAL-SOURCE-NOTICE.txt"] = (NOTICE.encode(), 0o644)
            files["REZAL-BUILD.md"] = (build_guide, 0o644)
            filename = f"{component}.tar.gz"
            digest = write_archive(stage / filename, files)
            source_info["components"][component] = {
                "repository": base_repository, "commit": base_commit,
                "image_digest": manifest[f"{component}_image"].split("@")[-1],
                "archive": f"releases/{release_name}/{filename}", "sha256": digest,
                "overlays": overlays,
            }
        # The public deployment snapshot contains the Compose files, Dockerfile,
        # settings, scripts and all original notices, without Git history.
        digest = write_archive(stage / "deployment.tar.gz", deployment)
        source_info["deployment_archive"] = {
            "archive": f"releases/{release_name}/deployment.tar.gz", "sha256": digest,
        }
        (stage / "source-manifest.json").write_text(json.dumps(source_info, indent=2) + "\n")
        sums = [f"{x['sha256']}  {Path(x['archive']).name}" for x in source_info["components"].values()]
        sums.append(f"{digest}  deployment.tar.gz")
        (stage / "SHA256SUMS").write_text("\n".join(sums) + "\n")
        (stage / "BUILD.md").write_bytes(build_guide)
        (stage / "LICENSE.txt").write_bytes(deployment["LICENSE"][0])
        stage.chmod(0o755)
        for p in stage.iterdir():
            p.chmod(0o644)
        if release_root.exists():
            # Never replace a different source release under the same URL.
            for p in stage.iterdir():
                if not (release_root / p.name).is_file() or (release_root / p.name).read_bytes() != p.read_bytes():
                    raise ValueError("immutable source release already exists with different content")
        else:
            os.replace(stage, release_root)
            # TemporaryDirectory expects its original directory to still exist.
            stage.mkdir()
    page = render_page(source_info, release_name)
    index_output = index_output or output / "index.html"
    index_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=index_output.parent, mode="w", encoding="utf-8", delete=False) as tmp:
        tmp.write(page)
        page_tmp = Path(tmp.name)
    page_tmp.chmod(0o644)
    os.replace(page_tmp, index_output)
    return source_info


def render_page(info: dict, release_name: str) -> str:
    links = []
    for component, spec in info["components"].items():
        links.append(f'<li><a href="{html.escape(spec["archive"])}">Télécharger les sources {component.capitalize()}</a>'
                     f'<p>Version : <code>{spec["commit"]}</code> — modifications du déploiement incluses.</p></li>')
    base = f"releases/{release_name}"
    return f'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Code source de cette instance — AGPLv3</title>
<style>body{{font:17px/1.6 system-ui,sans-serif;max-width:850px;margin:3rem auto;padding:0 1.2rem;color:#20242a;background:#fff}}a{{color:#1455a0}}code{{overflow-wrap:anywhere}}li{{margin:1rem 0}}p{{margin:.5rem 0}}</style></head>
<body><main><h1>Code source de cette instance</h1>
<p>Vous pouvez télécharger gratuitement les sources de cette version modifiée de TiBillet,
les étudier, les modifier et les redistribuer selon la licence GNU AGPLv3.</p>
<p>TiBillet est développé par ses auteurs, dont la coopérative Code Commun.
Cette instance utilise des personnalisations maintenues par Rezal-KIN.</p>
<h2>Sources de la version utilisée</h2><p>Release : <code>{html.escape(info['release_id'])}</code></p>
<ul>{''.join(links)}
<li><a href="{info['deployment_archive']['archive']}">Télécharger les scripts et fichiers de déploiement</a></li></ul>
<p><a href="{base}/BUILD.md">Instructions de reconstruction</a> ·
<a href="{base}/SHA256SUMS">Empreintes SHA-256 des archives</a> ·
<a href="{base}/source-manifest.json">Références exactes des sources</a></p>
<h2>Licence et auteurs</h2><p><a href="{base}/LICENSE.txt">Texte intégral de la licence AGPLv3</a> ·
<a href="https://github.com/Rezal-KIN/Tibillet">Dépôt du fork Rezal-KIN</a> ·
<a href="https://github.com/TiBillet/">Projets originaux TiBillet</a></p>
<p>Les mentions des auteurs et les licences des composants tiers sont conservées dans les archives.
Le logiciel est fourni sans garantie, dans les limites autorisées par la loi.</p>
</main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--deployment-commit", default="HEAD")
    parser.add_argument("--index-output", type=Path, help="prepare the index outside public/ until deployment is healthy")
    parser.add_argument("--verify-working-tree", action="store_true", help="refuse unversioned changes in deployment source")
    args = parser.parse_args()
    try:
        if args.verify_working_tree:
            verify_working_tree(args.repository, revision(args.repository, args.deployment_commit))
        info = build(args.repository, json.loads(args.manifest.read_text()),
                     json.loads(args.catalog.read_text()), args.output, args.cache, args.deployment_commit, args.index_output)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Source offer could not be built: {exc}") from exc
    print(f"Source offer built for {info['release_id']} from {info['deployment_commit']}")


if __name__ == "__main__":
    main()
