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
    allowed_updates = re.compile(
        r'^aws_iam_role_policy\.(?:active_switch_build|production_build|production_pipeline|production_validate|test_deploy)\["?[a-z0-9-]+"?\]$'
    )
    production_project = re.compile(r'^aws_codebuild_project\.production\["[a-z0-9-]+"\]$')
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ValueError("Terraform plan has no resource_changes array")
    changed: list[str] = []
    for item in changes:
        if not isinstance(item, dict) or not isinstance(item.get("address"), str):
            raise ValueError("malformed Terraform resource change")
        address = item["address"]
        actions = item.get("change", {}).get("actions")
        if item.get("mode") == "data" and actions in (["read"], ["no-op"]):
            continue
        if actions == ["no-op"]:
            continue
        if actions == ["create"] and (
            address.startswith(f'module.gala["{slug}"].') or address in allowed_new
        ):
            changed.append(f"create {address}")
            continue
        if actions == ["update"] and allowed_updates.fullmatch(address):
            change = item["change"]
            before = change.get("before")
            after = change.get("after")
            unknown = change.get("after_unknown")
            if (
                isinstance(before, dict) and isinstance(after, dict)
                and unknown == {"policy": True}
                and {k: v for k, v in before.items() if k != "policy"}
                == {k: v for k, v in after.items() if k != "policy"}
            ):
                changed.append(f"refresh-policy {address}")
                continue
            if address == 'aws_iam_role_policy.active_switch_build["apply"]' and safe_group_permission_addition(change):
                changed.append(f"add-managed-gala-group-permission {address}")
                continue
        if actions == ["update"] and production_project.fullmatch(address):
            change = item["change"]
            before = change.get("before")
            after = change.get("after")
            unknown = change.get("after_unknown", {})
            if isinstance(before, dict) and isinstance(after, dict) and not has_unknown(unknown):
                old_source = before.get("source")
                new_source = after.get("source")
                if (
                    {k: v for k, v in before.items() if k != "source"}
                    == {k: v for k, v in after.items() if k != "source"}
                    and isinstance(old_source, list) and isinstance(new_source, list)
                    and len(old_source) == len(new_source) == 1
                    and isinstance(old_source[0], dict) and isinstance(new_source[0], dict)
                    and old_source[0].get("buildspec") != new_source[0].get("buildspec")
                    and {k: v for k, v in old_source[0].items() if k != "buildspec"}
                    == {k: v for k, v in new_source[0].items() if k != "buildspec"}
                ):
                    changed.append(f"update-production-buildspec {address}")
                    continue
        raise ValueError(f"Foundation refuses {actions} on {address}")
    return changed


def has_unknown(value: object) -> bool:
    if isinstance(value, dict):
        return any(has_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(has_unknown(item) for item in value)
    return value is True


def safe_group_permission_addition(change: dict[str, object]) -> bool:
    before = change.get("before")
    after = change.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict) or has_unknown(change.get("after_unknown", {})):
        return False
    if {k: v for k, v in before.items() if k != "policy"} != {k: v for k, v in after.items() if k != "policy"}:
        return False
    try:
        old_policy = json.loads(before["policy"])
        new_policy = json.loads(after["policy"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return False
    if {k: v for k, v in old_policy.items() if k != "Statement"} != {k: v for k, v in new_policy.items() if k != "Statement"}:
        return False
    old_statements = old_policy.get("Statement")
    new_statements = new_policy.get("Statement")
    if not isinstance(old_statements, list) or not isinstance(new_statements, list):
        return False
    sid = "ReferenceOnlyKnownGalaSecurityGroups"
    added = [item for item in new_statements if isinstance(item, dict) and item.get("Sid") == sid]
    if len(added) != 1 or [item for item in new_statements if item not in added] != old_statements:
        return False
    statement = added[0]
    resources = statement.get("Resource")
    return (
        set(statement) == {"Sid", "Effect", "Action", "Resource"}
        and statement["Effect"] == "Allow"
        and statement["Action"] == "ec2:ModifyNetworkInterfaceAttribute"
        and isinstance(resources, list) and 2 <= len(resources) <= 20
        and all(isinstance(resource, str) for resource in resources)
        and len(resources) == len(set(resources))
        and all(re.fullmatch(r"arn:aws:ec2:eu-west-3:318629836660:security-group/sg-[0-9a-f]{8,17}", resource)
                for resource in resources)
    )


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
