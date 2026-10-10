"""Storage loss prevention and real SQLite backup behavior, including WAL."""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1] / "tools/runtime"
spec = importlib.util.spec_from_file_location("fedow_sqlite", RUNTIME / "fedow-sqlite.py")
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


def database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE django_migrations(id INTEGER PRIMARY KEY);
        CREATE TABLE fedow_core_configuration(id INTEGER PRIMARY KEY);
        CREATE TABLE fedow_core_wallet(id INTEGER PRIMARY KEY);
        CREATE TABLE fedow_core_token(id INTEGER PRIMARY KEY, wallet_id INTEGER REFERENCES fedow_core_wallet(id));
        CREATE TABLE fedow_core_transaction(id INTEGER PRIMARY KEY);
        CREATE TABLE fedow_core_card(id INTEGER PRIMARY KEY);
        INSERT INTO fedow_core_configuration VALUES (1);
        INSERT INTO fedow_core_wallet VALUES (1);
    """)
    db.execute("INSERT INTO fedow_core_token VALUES (1, 1)")
    db.commit()
    return db


class FedowSQLiteStorageTests(unittest.TestCase):
    def test_interrupted_first_boot_resumes_without_adopting_unknown_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, runtime = Path(tmp) / "repo", Path(tmp) / "runtime"
            sqlite, _pg, marker = storage.storage_paths(repo, runtime)
            storage.begin_initialization(repo, runtime)
            self.assertEqual(json.loads(marker.read_text())["state"], "initializing")
            db = database(sqlite)
            db.close()
            before = sqlite.read_bytes()
            storage.begin_initialization(repo, runtime)
            self.assertEqual(sqlite.read_bytes(), before)
            storage.initialize(repo, runtime)
            storage.begin_initialization(repo, runtime)
            self.assertEqual(json.loads(marker.read_text())["state"], "ready")
            self.assertEqual(sqlite.read_bytes(), before)

    def test_first_boot_marker_refuses_untracked_sqlite_and_postgres(self):
        for existing in ("sqlite", "postgres", "release"):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as tmp:
                repo, runtime = Path(tmp) / "repo", Path(tmp) / "runtime"
                sqlite, pg, marker = storage.storage_paths(repo, runtime)
                if existing == "sqlite":
                    db = database(sqlite)
                    db.close()
                elif existing == "postgres":
                    pg.mkdir(parents=True)
                    (pg / "PG_VERSION").write_text("13")
                else:
                    (runtime / "releases").mkdir(parents=True)
                    (runtime / "releases/deployed-manifest.json").write_text("{}")
                with self.assertRaisesRegex(ValueError, "explicit"):
                    storage.begin_initialization(repo, runtime)
                self.assertFalse(marker.exists())

    def test_snapshot_contains_committed_wal_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, saved = Path(tmp) / "live.sqlite3", Path(tmp) / "saved.sqlite3"
            with database(source) as db:
                # Source stays open: committed inserts are still in the WAL.
                self.assertTrue(Path(str(source) + "-wal").stat().st_size > 0)
                counts = storage.snapshot(source, saved)
                self.assertEqual(counts["fedow_core_token"], 1)
                db.execute("INSERT INTO fedow_core_token VALUES (2, 1)")
                db.commit()
                self.assertEqual(storage.verify(source)["fedow_core_token"], 2)
                self.assertEqual(storage.verify(saved)["fedow_core_token"], 1)
                with self.assertRaises(FileExistsError):
                    storage.snapshot(source, saved)
                self.assertEqual(storage.verify(saved)["fedow_core_token"], 1)
            db.close()

    def test_empty_start_is_explicit_and_old_postgresql_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, runtime = Path(tmp) / "repo", Path(tmp) / "runtime"
            sqlite, pg, marker = storage.storage_paths(repo, runtime)
            pg.mkdir(parents=True)
            (pg / "PG_VERSION").write_text("13")
            with self.assertRaisesRegex(ValueError, "explicit"):
                storage.check_storage(repo, runtime)
            storage.prepare_empty(repo, runtime)
            storage.check_storage(repo, runtime)
            self.assertEqual((pg / "PG_VERSION").read_text(), "13")
            db = database(sqlite)
            db.close()
            self.assertTrue(storage.initialize(repo, runtime, check_only=True))
            self.assertEqual(json.loads(marker.read_text())["state"], "initializing")
            # A failed first upload leaves this state, so a retry still knows
            # it needs a first SQLite backup, even with an old PG backup marker.
            self.assertTrue(storage.initialize(repo, runtime, check_only=True))
            storage.initialize(repo, runtime)
            self.assertEqual(json.loads(marker.read_text())["state"], "ready")
            storage.check_storage(repo, runtime)
            with self.assertRaisesRegex(ValueError, "never deletes"):
                storage.prepare_empty(repo, runtime)
            sqlite.unlink()
            with self.assertRaisesRegex(ValueError, "absent"):
                storage.check_storage(repo, runtime)

    def test_deployed_host_cannot_silently_initialize_empty_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, runtime = Path(tmp) / "repo", Path(tmp) / "runtime"
            repo.mkdir()
            storage.check_storage(repo, runtime)  # Genuine empty host.
            (runtime / "releases").mkdir(parents=True)
            (runtime / "releases/deployed-manifest.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "explicit"):
                storage.check_storage(repo, runtime)

    def test_invalid_foreign_keys_or_empty_configuration_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.sqlite3"
            db = database(path)
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("INSERT INTO fedow_core_token VALUES (2, 99)")
            db.commit()
            with self.assertRaisesRegex(ValueError, "foreign key"):
                storage.verify(path)
            db.execute("DELETE FROM fedow_core_token WHERE id=2")
            db.execute("DELETE FROM fedow_core_configuration")
            db.commit()
            with self.assertRaisesRegex(ValueError, "configuration"):
                storage.verify(path)
            db.close()

    def test_both_entrypoints_guard_storage_before_compose_up(self):
        for name in ("preflight.sh", "start-stacks.sh"):
            script = (RUNTIME / name).read_text()
            self.assertIn("check_fedow_storage", script)
        script = (RUNTIME / "start-stacks.sh").read_text()
        self.assertLess(script.index("check_fedow_storage"), script.index("up -d"))
        release = (RUNTIME / "deploy-release.sh").read_text()
        self.assertLess(release.index("begin-initialization"), release.index("up -d"))
        prepare = release.index("--check-only")
        upload = release.index('"$SCRIPT_DIR/backup-postgres.sh"', prepare)
        seal = release.index('"$SCRIPT_DIR/fedow-sqlite.py" initialize-storage', upload)
        self.assertLess(upload, seal)


if __name__ == "__main__":
    unittest.main()
