#!/usr/bin/env python3
"""Fail closed on any Terraform Foundation plan outside one Gala creation."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def verify(plan: dict[str, object], slug: str) -> list[str]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug):
        raise ValueError("invalid requested Gala slug")
    allowed_new = {
        f'aws_ssm_document.production_deploy["{slug}"]',
        f'aws_cloudwatch_log_group.production_deploy["{slug}"]',
        f'aws_iam_role.production_build["{slug}"]',
        f'aws_iam_role_policy.production_build["{slug}"]',
        f'aws_codebuild_project.production["{slug}"]',
        f'aws_iam_role.production_pipeline["{slug}"]',
        f'aws_iam_role_policy.production_pipeline["{slug}"]',
        f'aws_codepipeline.production["{slug}"]',
        f'aws_cloudwatch_log_group.production_validate["{slug}"]',
        f'aws_iam_role.production_validate["{slug}"]',
        f'aws_iam_role_policy.production_validate["{slug}"]',
        f'aws_codebuild_project.production_validate["{slug}"]',
    }
    allowed_updates = re.compile(r'^aws_iam_role_policy\.active_switch_build\["(plan|apply)"\]$')
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ValueError("Terraform plan has no resource_changes array")
    changed: list[str] = []
    for item in changes:
        if not isinstance(item, dict) or not isinstance(item.get("address"), str):
            raise ValueError("malformed Terraform resource change")
        address = item["address"]
        actions = item.get("change", {}).get("actions")
        if actions == ["no-op"]:
            continue
        if actions == ["create"] and (
            address.startswith(f'module.gala["{slug}"].') or address in allowed_new
        ):
            changed.append(f"create {address}")
            continue
        if actions == ["update"] and allowed_updates.fullmatch(address):
            changed.append(f"update {address}")
            continue
        raise ValueError(f"Foundation refuses {actions} on {address}")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args()
    changed = verify(json.loads(args.plan_json.read_text(encoding="utf-8")), args.slug)
    print(f"Foundation plan accepted: {len(changed)} resource changes")
    for change in changed:
        print(change)


if __name__ == "__main__":
    main()
