#!/usr/bin/env python3
"""SQLite snapshots and explicit storage adoption; no application writes."""

import argparse
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


def connect_readonly(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
        raise ValueError("Fedow SQLite file is absent, empty or a symlink")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def verify(path):
    with closing(connect_readonly(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("SQLite foreign key check failed")
        required = ("django_migrations", "fedow_core_configuration", "fedow_core_wallet",
                    "fedow_core_token", "fedow_core_transaction", "fedow_core_card")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(required) <= tables:
            raise ValueError("SQLite is missing native Fedow tables")
        if db.execute("SELECT count(*) FROM fedow_core_configuration").fetchone()[0] != 1:
            raise ValueError("SQLite has no unique initialized Fedow configuration")
        return {table: db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                for table in required}


def snapshot(source, destination):
    # Connection.backup includes committed WAL pages; copying db.sqlite3 alone
    # while the app is running does not. Never open the source in write mode.
    with destination.open("xb"):
        pass
    try:
        with closing(connect_readonly(source)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst, pages=256, sleep=0.05)
        return verify(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def storage_paths(repo, runtime):
    return (repo / "deploy/Fedow/sqlite-database/db.sqlite3",
            repo / "deploy/Fedow/database", runtime / "fedow-sqlite-storage.json")


def old_postgres_data(path):
    return path.exists() and (path.is_symlink() or any(path.iterdir()))


def read_marker(marker, database):
    record = json.loads(marker.read_text())
    if (marker.is_symlink() or not isinstance(record, dict) or record.get("schema_version") != 1
            or record.get("database") != str(database.resolve())
            or record.get("state") not in ("initializing", "ready")):
        raise ValueError("Fedow SQLite storage marker is invalid")
    return record


def check_storage(repo, runtime):
    database, old_pg, marker = storage_paths(repo, runtime)
    if marker.exists():
        record = read_marker(marker, database)
        if record["state"] == "ready":
            verify(database)
        # An explicit prepare-empty authorizes the native entrypoint to create
        # or finish a new DB. initialize-storage seals it after healthchecks.
    elif (old_postgres_data(old_pg) or (runtime / "releases/deployed-manifest.json").exists()
          or database.exists()):
        raise ValueError("Fedow SQLite is not initialized; existing Gala needs an explicit empty-storage preparation")
    # Only an empty host may use the native entrypoint to initialize a new DB.


def write_marker(marker, database, state):
    marker.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=marker.name + ".",
                                     dir=marker.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump({"schema_version": 1, "database": str(database.resolve()), "state": state}, handle)
        handle.write("\n")
    try:
        temporary.chmod(0o600)
        os.replace(temporary, marker)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_empty(repo, runtime):
    database, _old_pg, marker = storage_paths(repo, runtime)
    if marker.exists() or database.exists() or database.is_symlink():
        raise ValueError("SQLite storage already exists; prepare-empty never deletes or replaces it")
    # Deliberate operator action. The former PostgreSQL bind data is untouched.
    write_marker(marker, database, "initializing")


def initialize(repo, runtime, check_only=False):
    database, old_pg, marker = storage_paths(repo, runtime)
    if marker.exists():
        record = read_marker(marker, database)
        if record["state"] == "ready":
            verify(database)
            return False
    else:
        if old_postgres_data(old_pg) or (runtime / "releases/deployed-manifest.json").exists():
            raise ValueError("An existing Gala needs an explicit empty-storage preparation")
    verify(database)
    if not check_only:
        write_marker(marker, database, "ready")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "snapshot"):
        command = sub.add_parser(name)
        command.add_argument("database", type=Path)
        if name == "snapshot":
            command.add_argument("destination", type=Path)
    for name in ("check-storage", "prepare-empty", "initialize-storage"):
        command = sub.add_parser(name)
        command.add_argument("repo", type=Path)
        command.add_argument("runtime", type=Path)
        if name == "initialize-storage":
            command.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.command == "verify":
        print(json.dumps(verify(args.database), sort_keys=True))
    elif args.command == "snapshot":
        print(json.dumps(snapshot(args.database, args.destination), sort_keys=True))
    elif args.command == "check-storage":
        check_storage(args.repo, args.runtime)
    elif args.command == "prepare-empty":
        prepare_empty(args.repo, args.runtime)
    else:
        print("initialized" if initialize(args.repo, args.runtime, args.check_only) else "ready")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, sqlite3.Error) as exc:
        raise SystemExit(f"Fedow SQLite: {exc}") from None
