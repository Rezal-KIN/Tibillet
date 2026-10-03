from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("source_offer", ROOT / "tools/build-source-offer.py")
offer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offer)


def upstream_archive(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, content in files.items():
            data = content.encode()
            entry = tarfile.TarInfo("upstream/" + name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return stream.getvalue()


class SourceOfferTests(unittest.TestCase):
    def test_template_directories_support_each_upstream_base_dir_type(self):
        # Evaluate the actual settings declarations without starting Django or
        # importing production integrations. Laboutik's BASE_DIR is a string,
        # whereas Fedow's is a pathlib.Path.
        for component in ("Fedow", "Laboutik"):
            settings_path = ROOT / component / "settings.py"
            tree = ast.parse(settings_path.read_text())
            declarations = [node for node in tree.body if isinstance(node, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id in {"BASE_DIR", "TEMPLATES"}
                                    for target in node.targets)]
            namespace = {"__file__": str(settings_path), "os": os, "Path": Path}
            exec(compile(ast.Module(body=declarations, type_ignores=[]), str(settings_path), "exec"), namespace)
            dirs = namespace["TEMPLATES"][0]["DIRS"]
            self.assertEqual([Path(value) for value in dirs], [Path(namespace["BASE_DIR"]) / "source_templates"])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repository"
        self.repo.mkdir()
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.output = self.root / "public"
        files = {
            "LICENSE": "GNU AGPL version 3\n",
            "AUTHORS.md": "Original Code Commun authors\n",
            "main.py": "print('source')\n",
            "deploy/Fedow/.env.example": "SECRET_KEY=\n",
            "deploy/Laboutik/.env.example": "SECRET_KEY=\n",
            "deploy/Fedow/patch.py": "print('gala')\n",
            "deploy/Fedow/docker-compose.yml": "services:\n  app:\n    volumes:\n      - ./patch.py:/home/fedow/Fedow/core.py:ro\n      - ../source/admin-templates:/home/fedow/Fedow/source_templates:ro\n",
            "deploy/Laboutik/docker-compose.yml": "services: {}\n",
            "deploy/source/admin-templates/admin/base_site.html": "source offer\n",
            "deploy/source/BUILD.md": "Build instructions from the pinned public commit\n",
            ".env": "private-production-value\n",
            ".context/mail.pdf": "private correspondence\n",
            "logs/client.log": "private runtime log\n",
            "backup/users.sql": "private database\n",
            "backup/save.sh": "#!/bin/sh\necho backup\n",
        }
        for name, content in files.items():
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "source fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.manifest = {
            "application_repository": "Rezal-KIN/Tibillet", "release_id": "gala-v1.0.1",
            "fork_commit": self.commit,
            **{name + "_image": "example/" + name + "@sha256:" + "a" * 64 for name in ["lespass", "fedow", "laboutik"]},
        }
        self.catalog = {}
        for component, repository in [("fedow", "TiBillet/Fedow"), ("laboutik", "TiBillet/LaBoutik")]:
            data = upstream_archive({"core.py": "print('upstream')\n", "LICENSE": "upstream license\n",
                                     "env_test2": "private upstream environment\n", "backup/save.sh": "echo backup\n"})
            self.catalog[component] = {"repository": repository, "commit": "b" * 40,
                "image": self.manifest[component + "_image"], "archive_sha256": hashlib.sha256(data).hexdigest()}
            (self.cache / (repository.replace("/", "-") + "-" + "b" * 40 + ".tar.gz")).write_bytes(data)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True)

    def build(self, **kwargs):
        return offer.build(self.repo, self.manifest, self.catalog, self.output, self.cache, **kwargs)

    def test_archives_match_pinned_sources_and_mounts_without_private_data(self):
        # This local edit must NOT enter the source package for the Git commit.
        (self.repo / "main.py").write_text("uncommitted local change")
        info = self.build()
        for name, component in info["components"].items():
            archive_path = self.output / component["archive"]
            self.assertEqual(hashlib.sha256(archive_path.read_bytes()).hexdigest(), component["sha256"])
            files = offer.read_archive(archive_path.read_bytes(), strip_root=True)
            self.assertNotIn(".env", files)
            self.assertNotIn("env_test2", files)
            self.assertNotIn(".context/mail.pdf", files)
            self.assertNotIn("logs/client.log", files)
            self.assertNotIn("backup/users.sql", files)
            self.assertIn("backup/save.sh", files)
            if name == "lespass":
                self.assertEqual(files["main.py"][0], b"print('source')\n")
            if name == "fedow":
                self.assertEqual(files["core.py"][0], b"print('gala')\n")
                self.assertIn("source_templates/admin/base_site.html", files)
                self.assertEqual(files["LICENSE"][0], b"upstream license\n")
            self.assertEqual(archive_path.stat().st_mode & 0o777, 0o644)
            self.assertEqual(archive_path.parent.stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.output / "index.html").stat().st_mode & 0o777, 0o644)
        self.assertNotIn("private-production-value", json.dumps(info))

    def test_unknown_image_or_corrupt_original_stops_publication(self):
        self.manifest["fedow_image"] = "example/fedow@sha256:" + "c" * 64
        with self.assertRaisesRegex(ValueError, "not audited"):
            self.build()
        self.assertFalse((self.output / "index.html").exists())
        self.manifest["fedow_image"] = self.catalog["fedow"]["image"]
        self.catalog["fedow"]["archive_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.build()

    def test_missing_mounted_source_stops_publication(self):
        self.git("rm", "-q", "deploy/Fedow/patch.py")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "missing mounted source")
        with self.assertRaises(KeyError):
            self.build()

    def test_retry_keeps_archives_immutable_and_preparation_keeps_current_index(self):
        info = self.build()
        current = (self.output / "index.html").read_bytes()
        prepared = self.root / "next-index.html"
        self.assertEqual(self.build(index_output=prepared), info)
        self.assertEqual((self.output / "index.html").read_bytes(), current)
        self.assertEqual(prepared.read_bytes(), current)
        archive = self.output / info["components"]["lespass"]["archive"]
        archive.write_bytes(b"corrupt existing release")
        with self.assertRaisesRegex(ValueError, "different content"):
            self.build()

    def test_archive_traversal_is_rejected(self):
        data = upstream_archive({"../escape.py": "unsafe"})
        with self.assertRaisesRegex(ValueError, "unsafe"):
            offer.read_archive(data, strip_root=True)

    def test_runtime_refuses_a_mount_changed_outside_git(self):
        offer.verify_working_tree(self.repo, self.commit)
        (self.repo / "deploy/Fedow/patch.py").write_text("uncommitted effective code")
        with self.assertRaisesRegex(ValueError, "differs from its Git revision"):
            offer.verify_working_tree(self.repo, self.commit)

    def test_github_page_links_to_all_assets_off_the_instance(self):
        info = self.build()
        release_name = Path(info["deployment_archive"]["archive"]).parent.name
        page = offer.render_page(info, release_name, github_release=True)
        base = f"https://github.com/Rezal-KIN/Tibillet/releases/download/sources-{release_name}/"
        for name in ("lespass.tar.gz", "fedow.tar.gz", "laboutik.tar.gz", "deployment.tar.gz",
                     "BUILD.md", "LICENSE.txt", "SHA256SUMS", "source-manifest.json"):
            self.assertIn(f'href="{base}{name}"', page)
        self.assertIn("restent accessibles lorsque cette instance est arrêtée", page)

    def test_github_gate_rejects_missing_or_mismatched_public_assets(self):
        info = self.build()
        release_name = Path(info["deployment_archive"]["archive"]).parent.name
        root = self.output / "releases" / release_name
        tag = offer.github_release_tag(release_name)
        release = {"tag_name": tag, "draft": False, "assets": [
            {"name": path.name, "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
             "browser_download_url": f"https://github.com/Rezal-KIN/Tibillet/releases/download/{tag}/{path.name}"}
            for path in root.iterdir()
        ]}
        def check():
            with patch.object(offer.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(release).encode())):
                offer.verify_github_release(root, release_name)
        check()
        asset = release["assets"].pop()
        with self.assertRaisesRegex(ValueError, "missing"):
            check()
        release["assets"].append({**asset, "digest": "sha256:" + "0" * 64})
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            check()


if __name__ == "__main__":
    unittest.main()
