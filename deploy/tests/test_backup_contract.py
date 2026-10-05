from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[1] / "tools/runtime"


class BackupContractTests(unittest.TestCase):
    def test_backup_checksums_are_portable_after_upload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            saved = root / "uploaded"
            docker = bin_dir / "docker"
            docker.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  inspect) case \"$3\" in *Mounts*) printf '%s' \"${MOCK_FEDOW_MOUNT:-}\" ;; *Config.Image*) echo postgres:13-bookworm ;; *Running*) echo true ;; esac; exit 0 ;;\n"
                "  exec) printf 'CREATE TABLE backed_up (id integer);\\n'; exit 0 ;;\n"
                "esac\nexit 2\n",
                encoding="utf-8",
            )
            aws = bin_dir / "aws"
            aws.write_text(
                "#!/bin/sh\n"
                "[ \"$1 $2 $3 $4\" = 's3 cp --only-show-errors --recursive' ] || exit 2\n"
                "mkdir -p \"$MOCK_UPLOADED\"\n"
                "cp \"$5\"/* \"$MOCK_UPLOADED\"/\n",
                encoding="utf-8",
            )
            docker.chmod(0o755)
            aws.chmod(0o755)
            config = root / "gala.conf"
            config.write_text(
                f'GALA_SLUG="gala-verification"\nAWS_REGION="eu-west-3"\n'
                f'BACKUP_BUCKET="test-bucket"\nREPO_ROOT="{root}"\n'
                f'RUNTIME_ROOT="{root / "runtime"}"\n'
                'POSTGRES_CONTAINERS="fedow_postgres,laboutik_postgres,lespass_postgres"\n',
                encoding="utf-8",
            )
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
                   "MOCK_UPLOADED": str(saved)}
            command = ["bash", str(RUNTIME / "backup-postgres.sh"), str(config)]
            result = subprocess.run(command,
                                    env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "runtime/gala-verification/last-successful-backup").is_file())
            self.assertEqual(len(list(saved.glob("*.sql.gz"))), 3)
            sums = (saved / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertNotIn(str(root), sums)
            checked = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=saved,
                                     text=True, capture_output=True, check=False)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            # Same historical config after cutover: Fedow must become a SQLite
            # snapshot, rather than trying to dump the removed PG container.
            mount = root / "deploy/Fedow/sqlite-database"
            mount.mkdir(parents=True)
            db = sqlite3.connect(mount / "db.sqlite3")
            db.execute("PRAGMA journal_mode=WAL")
            for table in ("django_migrations", "fedow_core_configuration", "fedow_core_wallet",
                          "fedow_core_token", "fedow_core_transaction", "fedow_core_card"):
                db.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
                db.execute(f'INSERT INTO "{table}" VALUES (1)')
            db.commit()
            hybrid = root / "hybrid"
            env.update(MOCK_UPLOADED=str(hybrid), MOCK_FEDOW_MOUNT=str(mount))
            result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            db.close()
            self.assertEqual(len(list(hybrid.glob("*.sql.gz"))), 2)
            self.assertTrue((hybrid / "fedow.sqlite3.gz").is_file())
            self.assertIn("fedow_sqlite=1", (hybrid / "metadata.txt").read_text())
            checked = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=hybrid,
                                     text=True, capture_output=True, check=False)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            # A missing active SQLite must fail without replacing the last
            # successful backup or silently creating an empty database.
            backup_marker = root / "runtime/gala-verification/last-successful-backup"
            previous_marker = backup_marker.read_bytes()
            (mount / "db.sqlite3").unlink()
            result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(backup_marker.read_bytes(), previous_marker)
            self.assertFalse((mount / "db.sqlite3").exists())

    def test_initial_deploy_exception_ends_with_first_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            docker = bin_dir / "docker"
            docker.write_text("#!/bin/sh\n[ \"$1\" = compose ] || exit 2\n", encoding="utf-8")
            docker.chmod(0o755)
            compose = root / "docker-compose.yml"
            compose.write_text("services: {}\n", encoding="utf-8")
            config = root / "gala.conf"
            config.write_text(
                f'GALA_SLUG="gala-verification"\nAWS_REGION="eu-west-3"\n'
                f'BACKUP_BUCKET="test-bucket"\nREPO_ROOT="{root}"\n'
                f'RUNTIME_ROOT="{root / "runtime"}"\nCOMPOSE_FILES="{compose}"\n'
                'POSTGRES_CONTAINERS="fedow_postgres"\nPLATFORM="v1"\n'
                'FEDOW_PUBLIC_DOMAIN="fedow.galas-am-aix.rezal.fr"\n'
                'LABOUTIK_PUBLIC_DOMAIN="cashless.galas-am-aix.rezal.fr"\n'
                'LESPASS_PUBLIC_DOMAIN="galas-am-aix.rezal.fr"\n'
                'DEPLOYMENT_LOCKED=false\nALLOW_INITIAL_DEPLOY=true\nMIN_FREE_SPACE_KIB=0\n',
                encoding="utf-8",
            )
            manifest = root / "release.json"
            manifest.write_text(json.dumps({
                "release_id": "test", "gala_slug": "gala-verification", "platform": "v1",
                "application_repository": "Rezal-KIN/Tibillet", "fork_commit": "a" * 40,
                "tibillet_upstream_commit": "a" * 40, "schema_generation": "v1",
                **{key: "example/image@sha256:" + "a" * 64 for key in (
                    "lespass_image", "fedow_image", "laboutik_image", "traefik_image")},
            }), encoding="utf-8")
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            command = ["bash", str(RUNTIME / "preflight.sh"), str(config), str(manifest)]
            initial = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(initial.returncode, 0, initial.stderr)
            release_dir = root / "runtime/gala-verification/releases"
            release_dir.mkdir(parents=True, exist_ok=True)
            (release_dir / "deployed-manifest.json").write_text("{}", encoding="utf-8")
            later = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
            self.assertNotEqual(later.returncode, 0)
            self.assertIn("no successful backup marker exists", later.stderr)


if __name__ == "__main__":
    unittest.main()
