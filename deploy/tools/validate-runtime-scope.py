#!/usr/bin/env python3
"""Reject AWS/runtime targets outside the versioned Gala scope policy."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "ops/policy/runtime-allowlist.yaml"
DENYLIST = ROOT / "ops/policy/denied-targets.yaml"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_allowlist() -> tuple[str, str, set[str], set[str]]:
    account_id = ""
    region = ""
    ids: set[str] = set()
    names: set[str] = set()
    current_key = ""

    for raw_line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("aws_account_id:"):
            account_id = line.partition(":")[2].strip().strip('"')
            current_key = ""
        elif line.startswith("runtime_region:"):
            region = line.partition(":")[2].strip().strip('"')
            current_key = ""
        elif line == "instances:":
            current_key = "instances"
        elif current_key == "instances" and line.startswith("- id:"):
            ids.add(line.partition(":")[2].strip())
        elif current_key == "instances" and line.startswith("name:"):
            names.add(line.partition(":")[2].strip())

    if not account_id or not region or not ids or not names:
        fail(f"invalid allowlist: {ALLOWLIST}")
    return account_id, region, ids, names


def read_denied_references() -> set[str]:
    denied: set[str] = set()
    for raw_line in DENYLIST.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            denied.add(line.removeprefix("- "))
    if not denied:
        fail(f"invalid denylist: {DENYLIST}")
    return denied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--instance-name", required=True)
    parser.add_argument("--reference", action="append", default=[])
    args = parser.parse_args()

    account_id, region, instance_ids, instance_names = read_allowlist()
    denied = read_denied_references()

    if args.account != account_id:
        fail(f"AWS account {args.account} is outside the Gala allowlist")
    if args.region != region:
        fail(f"AWS region {args.region} is outside the Gala runtime allowlist")
    if args.instance not in instance_ids:
        fail(f"instance {args.instance} is outside the Gala runtime allowlist")
    if args.instance_name not in instance_names:
        fail(f"instance name {args.instance_name} is outside the Gala runtime allowlist")

    for reference in args.reference:
        if reference in denied:
            fail(f"reference is explicitly denied by policy: {reference}")

    print(f"Runtime scope valid: {args.instance_name} ({args.instance})")


if __name__ == "__main__":
    main()
