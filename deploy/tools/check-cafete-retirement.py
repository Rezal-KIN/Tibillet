#!/usr/bin/env python3
"""Read-only preconditions for retiring the one archived November cafete host."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


ACCOUNT = "318629836660"
REGION = "eu-west-3"
OLD_SLUG = "bapts2026"
OLD_INSTANCE = "i-0a3f206386b2c81ca"
OLD_VOLUME = "vol-08fee254e12be2834"
NEW_SLUG = "bapts2026-gala-20261127"
NEW_INSTANCE = "i-0f10b4463813cec44"
BUCKET = "tibillet-gala-paris-production-318629836660-backups"
BACKUP_ID = "20261125T115449Z"
PREFIX = f"galas/{OLD_SLUG}/postgres/{BACKUP_ID}/"
BACKUP_COMMAND = "c3d64c70-b215-416c-968a-ee486f86c171"
RESTORE_COMMAND = "7f4c3ece-0bb3-4ff2-a429-3885c1e18092"
FILES = {"lespass_postgres.sql.gz", "laboutik_postgres.sql.gz", "fedow.sqlite3.gz", "metadata.txt"}


def aws(*arguments):
    result = subprocess.run(["aws", *arguments, "--region", REGION, "--output", "json"],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("read-only cafete retirement precondition failed: " + arguments[0] + "/" + arguments[1])
    return json.loads(result.stdout)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def verify():
    require(aws("sts", "get-caller-identity").get("Account") == ACCOUNT, "wrong account")
    marker = aws("ssm", "get-parameter", "--name", "/tibillet-gala-paris/active-gala")
    require(marker.get("Parameter", {}).get("Value") == NEW_SLUG, "replacement Gala is not active")
    instances = aws("ec2", "describe-instances", "--instance-ids", OLD_INSTANCE, NEW_INSTANCE)
    hosts = {host["InstanceId"]: host for group in instances["Reservations"] for host in group["Instances"]}
    for identity, slug, state in ((OLD_INSTANCE, OLD_SLUG, "stopped"), (NEW_INSTANCE, NEW_SLUG, "running")):
        host = hosts.get(identity, {})
        tags = {item["Key"]: item["Value"] for item in host.get("Tags", [])}
        require(host.get("State", {}).get("Name") == state, "unexpected event instance state")
        require(tags.get("Gala") == slug and tags.get("Project") == "tibillet-gala-paris"
                and tags.get("ManagedBy") == "terraform", "event instance identity changed")
    addresses = aws("ec2", "describe-addresses", "--public-ips", "51.44.90.200")["Addresses"]
    require(len(addresses) == 1 and addresses[0].get("InstanceId") == NEW_INSTANCE,
            "production EIP does not belong to the replacement")
    require(not aws("ec2", "describe-addresses", "--filters", f"Name=instance-id,Values={OLD_INSTANCE}")["Addresses"],
            "old event still has an EIP")
    volumes = aws("ec2", "describe-volumes", "--volume-ids", OLD_VOLUME)["Volumes"]
    require(len(volumes) == 1 and volumes[0].get("Encrypted") is True and volumes[0].get("Size") == 40
            and any(a.get("InstanceId") == OLD_INSTANCE for a in volumes[0].get("Attachments", [])),
            "old encrypted root volume identity changed")

    backup = aws("ssm", "get-command-invocation", "--command-id", BACKUP_COMMAND, "--instance-id", OLD_INSTANCE)
    require(backup.get("Status") == "Success" and backup.get("ResponseCode") == 0
            and f"gala={OLD_SLUG} backup_id={BACKUP_ID} postgres=2 sqlite=1" in backup.get("StandardOutputContent", ""),
            "approved database upload proof is missing")
    restore = aws("ssm", "get-command-invocation", "--command-id", RESTORE_COMMAND, "--instance-id", OLD_INSTANCE)
    require(restore.get("Status") == "Success" and restore.get("ResponseCode") == 0,
            "successful isolated restore proof is missing")
    for source in ("lespass_postgres", "laboutik_postgres", "fedow_sqlite"):
        require(f"gala={OLD_SLUG} backup_id={BACKUP_ID} source={source}" in restore.get("StandardOutputContent", ""),
                "isolated restore does not cover all three event databases")
    restored_at = timestamp(restore["ExecutionEndDateTime"])
    for filename in FILES | {"SHA256SUMS"}:
        head = aws("s3api", "head-object", "--bucket", BUCKET, "--key", PREFIX + filename)
        require(head.get("ServerSideEncryption") == "AES256" and head.get("VersionId")
                and head.get("ContentLength", 0) > 0 and timestamp(head["LastModified"]) <= restored_at,
                "archive object missing, unencrypted or changed after the restore drill")
    with tempfile.TemporaryDirectory(prefix="cafete-retirement-proof-") as directory:
        paths = {}
        for filename in ("metadata.txt", "SHA256SUMS"):
            path = Path(directory) / filename
            aws("s3api", "get-object", "--bucket", BUCKET, "--key", PREFIX + filename, str(path))
            paths[filename] = path
        metadata = paths["metadata.txt"].read_text().splitlines()
        require(f"gala={OLD_SLUG}" in metadata and f"backup_id={BACKUP_ID}" in metadata
                and "fedow_sqlite=1" in metadata and "backup_format=2" in metadata,
                "archive belongs to a different event or storage engine")
        lines = paths["SHA256SUMS"].read_text().splitlines()
        require(len(lines) == 4 and all(re.fullmatch(r"[0-9a-f]{64}  [a-zA-Z0-9_.-]+", line) for line in lines),
                "invalid archive checksum list")
        checksums = {line.split()[1]: line.split()[0] for line in lines}
        require(set(checksums) == FILES, "archive checksum list does not cover the three databases")
        require(hashlib.sha256(paths["metadata.txt"].read_bytes()).hexdigest() == checksums["metadata.txt"],
                "archive metadata checksum mismatch")
    print("Cafete retirement prerequisites verified: stopped old host, active replacement, restored private DB archive")


if __name__ == "__main__":
    verify()
