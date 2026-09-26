#!/usr/bin/env python3
"""Fail closed on Terraform Foundation plans outside approved operations."""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
from pathlib import Path


VALIDATION_SLUGS = ("gala-validation", "gala-validation-2")
RETIREMENT_OPERATIONS = {
    "Prepare Validation Retirement": "prepare",
    "Retire Validation Instances": "retire",
}
VERIFICATION_RETIREMENT_OPERATIONS = {
    "Prepare Gala Verification Retirement": "prepare",
    "Retire Gala Verification": "retire",
}
VERIFICATION_SLUG = "gala-verification"
VERIFICATION_INSTANCE_ID = "i-0f8d460abd9ba41d9"
VERIFICATION_VOLUME_ID = "vol-0643159830aff7cd1"
FIRST_RUN_SLUG = "gala-first-run-20260926"
FIRST_RUN_INSTANCE_ID = "i-0f32df17b219428dd"
FIRST_RUN_VOLUME_ID = "vol-06682cc1dace8854f"
FIRST_RUN_RETIREMENT_OPERATIONS = {
    "Prepare Gala First Run Retirement": "prepare",
    "Retire Gala First Run": "retire",
}
TEMPORARY_IDENTITIES = {
    VERIFICATION_SLUG: (VERIFICATION_INSTANCE_ID, VERIFICATION_VOLUME_ID),
    FIRST_RUN_SLUG: (FIRST_RUN_INSTANCE_ID, FIRST_RUN_VOLUME_ID),
}


def verify_validation_retirement_plan(
    plan: dict[str, object], phase: str, targets: tuple[str, ...] = VALIDATION_SLUGS,
) -> list[str]:
    """Permit only exact disposable hosts through the two-step retirement."""
    if phase not in {"prepare", "retire"}:
        raise ValueError("invalid validation retirement phase")
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ValueError("Terraform plan has no resource_changes array")
    accepted: list[str] = []
    seen: set[str] = set()
    policy_change: dict[str, object] | None = None
    removed_resources: set[str] = set()
    for item in changes:
        if not isinstance(item, dict) or not isinstance(item.get("address"), str):
            raise ValueError("malformed Terraform resource change")
        address = item["address"]
        change = item.get("change")
        if not isinstance(change, dict):
            raise ValueError(f"malformed Terraform change on {address}")
        actions = change.get("actions")
        if actions == ["no-op"] or (item.get("mode") == "data" and actions == ["read"]):
            continue
        if phase == "retire" and address == 'aws_iam_role_policy.active_switch_build["apply"]' and actions == ["update"]:
            if policy_change is not None:
                raise ValueError("duplicate active switch policy update")
            policy_change = change
            continue
        slug = next((value for value in targets
                     if address == f'module.gala["{value}"].aws_instance.retirable[0]'), None)
        if slug is None or slug in seen:
            raise ValueError(f"validation retirement refuses {actions} on {address}")
        seen.add(slug)
        before = change.get("before")
        after = change.get("after")
        if not isinstance(before, dict):
            raise ValueError(f"missing existing EC2 state on {address}")
        tags = before.get("tags")
        blocks = before.get("root_block_device")
        if slug in TEMPORARY_IDENTITIES and (
            before.get("id") != TEMPORARY_IDENTITIES[slug][0]
            or not isinstance(blocks, list) or len(blocks) != 1
            or not isinstance(blocks[0], dict)
            or blocks[0].get("volume_id") != TEMPORARY_IDENTITIES[slug][1]
        ):
            raise ValueError("temporary Gala EC2 or root volume identity changed")
        if (not isinstance(tags, dict) or tags.get("Project") != "tibillet-gala-paris"
                or tags.get("Gala") != slug or tags.get("ManagedBy") != "terraform"
                or not isinstance(blocks, list) or len(blocks) != 1
                or not isinstance(blocks[0], dict) or blocks[0].get("volume_size") != 40):
            raise ValueError(f"unexpected validation EC2 identity on {address}")
        if phase == "prepare":
            if actions != ["update"] or not isinstance(after, dict) or change.get("after_unknown", {}) != {}:
                raise ValueError(f"unsafe validation preparation on {address}")
            old_address = f'module.gala["{slug}"].aws_instance.runtime[0]'
            if item.get("previous_address") not in (None, old_address):
                raise ValueError(f"unexpected moved source on {address}")
            new_blocks = after.get("root_block_device")
            if (before.get("disable_api_termination") is not True
                    or after.get("disable_api_termination") is not False
                    or blocks[0].get("delete_on_termination") is not False
                    or not isinstance(new_blocks, list) or len(new_blocks) != 1
                    or not isinstance(new_blocks[0], dict)
                    or new_blocks[0].get("delete_on_termination") is not True
                    or {key: value for key, value in before.items() if key not in {"disable_api_termination", "root_block_device"}}
                    != {key: value for key, value in after.items() if key not in {"disable_api_termination", "root_block_device"}}
                    or {key: value for key, value in blocks[0].items() if key != "delete_on_termination"}
                    != {key: value for key, value in new_blocks[0].items() if key != "delete_on_termination"}):
                raise ValueError(f"unsafe validation preparation on {address}")
            accepted.append(f"prepare-validation-instance {address}")
        elif (actions == ["delete"] and after is None
              and item.get("previous_address") is None
              and before.get("disable_api_termination") is False
              and blocks[0].get("delete_on_termination") is True):
            instance_id = before.get("id")
            eni_id = before.get("primary_network_interface_id")
            if not (isinstance(instance_id, str) and re.fullmatch(r"i-[0-9a-f]{8,17}", instance_id)
                    and isinstance(eni_id, str) and re.fullmatch(r"eni-[0-9a-f]{8,17}", eni_id)):
                raise ValueError(f"invalid retiring EC2 identifiers on {address}")
            removed_resources.add(f"arn:aws:ec2:eu-west-3:318629836660:instance/{instance_id}")
            removed_resources.add(f"arn:aws:ec2:eu-west-3:318629836660:network-interface/{eni_id}")
            accepted.append(f"retire-validation-instance {address}")
        else:
            raise ValueError(f"unsafe validation deletion on {address}")
    if policy_change is not None:
        if not safe_validation_policy_removal(policy_change, removed_resources):
            raise ValueError("unsafe active switch policy update during validation retirement")
        accepted.append('remove-retired-host-permissions aws_iam_role_policy.active_switch_build["apply"]')
    if seen != set(targets):
        raise ValueError("retirement plan does not contain every exact target EC2")
    return accepted


def verify_verification_retirement_plan(
    plan: dict[str, object], phase: str, slug: str = VERIFICATION_SLUG,
) -> list[str]:
    if slug not in TEMPORARY_IDENTITIES:
        raise ValueError("unknown temporary Gala retirement target")
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ValueError("Terraform plan has no resource_changes array")
    instance_address = f'module.gala["{slug}"].aws_instance.retirable[0]'
    switch_policy = 'aws_iam_role_policy.active_switch_build["apply"]'
    allowed_delivery_deletions = {
        f'{kind}["{slug}"]' for kind in (
            "aws_ssm_document.production_deploy",
            "aws_iam_role_policy.production_build",
            "aws_codebuild_project.production",
            "aws_iam_role_policy.production_pipeline",
            "aws_codepipeline.production",
            "aws_iam_role_policy.production_validate",
            "aws_codebuild_project.production_validate",
        )
    }
    # Terraform defers these unchanged policy documents while their referenced
    # production resources are being removed. The only acceptable change is a
    # provider-computed policy value; all identity and other fields must match.
    allowed_policy_refreshes = {
        'aws_iam_role_policy.production_build["gala-am-aix"]',
        'aws_iam_role_policy.production_pipeline["gala-am-aix"]',
        'aws_iam_role_policy.test_deploy[0]',
    }
    core: list[dict[str, object]] = []
    accepted: list[str] = []
    for item in changes:
        if not isinstance(item, dict) or not isinstance(item.get("address"), str):
            raise ValueError("malformed Terraform resource change")
        address = item["address"]
        change = item.get("change")
        if not isinstance(change, dict):
            raise ValueError(f"malformed Terraform change on {address}")
        actions = change.get("actions")
        if actions == ["no-op"] or (item.get("mode") == "data" and actions == ["read"]):
            continue
        if address in {instance_address, switch_policy}:
            core.append(item)
        elif (phase == "retire" and address in allowed_policy_refreshes
              and actions == ["update"] and safe_computed_policy_refresh(change)):
            accepted.append(f"refresh-unrelated-delivery-policy {address}")
        elif (phase == "retire" and address in allowed_delivery_deletions
              and actions == ["delete"] and change.get("after") is None
              and isinstance(change.get("before"), dict)):
            accepted.append(f"retire-temporary-delivery {address}")
        else:
            raise ValueError(f"temporary Gala retirement refuses {actions} on {address}")
    accepted.extend(verify_validation_retirement_plan(
        {"resource_changes": core}, phase, targets=(slug,),
    ))
    return accepted


def safe_computed_policy_refresh(change: dict[str, object]) -> bool:
    before = change.get("before")
    after = change.get("after")
    return (
        isinstance(before, dict) and isinstance(after, dict)
        and isinstance(before.get("policy"), str)
        and after.get("policy") is None
        and change.get("after_unknown") == {"policy": True}
        and {key: value for key, value in before.items() if key != "policy"}
        == {key: value for key, value in after.items() if key != "policy"}
    )


def safe_validation_policy_removal(change: dict[str, object], removed_resources: set[str]) -> bool:
    before = change.get("before")
    after = change.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict) or has_unknown(change.get("after_unknown", {})):
        return False
    if {k: v for k, v in before.items() if k != "policy"} != {k: v for k, v in after.items() if k != "policy"}:
        return False
    try:
        old = json.loads(before["policy"])
        new = json.loads(after["policy"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return False
    if {k: v for k, v in old.items() if k != "Statement"} != {k: v for k, v in new.items() if k != "Statement"}:
        return False
    old_statements = old.get("Statement")
    new_statements = new.get("Statement")
    if not isinstance(old_statements, list) or not isinstance(new_statements, list) or len(old_statements) != len(new_statements):
        return False
    changed_sids: set[str] = set()
    for prior, later in zip(old_statements, new_statements):
        if prior == later:
            continue
        if not isinstance(prior, dict) or not isinstance(later, dict):
            return False
        sid = prior.get("Sid")
        if sid not in {"MoveOnlyTheSharedGalaEip", "ChangeOnlyKnownGalaNetworkInterfaces", "RunReadOnlyTargetHealthcheck"}:
            return False
        if {k: v for k, v in prior.items() if k != "Resource"} != {k: v for k, v in later.items() if k != "Resource"}:
            return False
        old_resources = prior.get("Resource")
        new_resources = later.get("Resource")
        if not isinstance(old_resources, list) or not isinstance(new_resources, list):
            return False
        removed = set(old_resources) - set(new_resources)
        if (len(old_resources) != len(set(old_resources)) or len(new_resources) != len(set(new_resources))
                or not removed or not removed <= removed_resources
                or [resource for resource in old_resources if resource not in removed] != new_resources):
            return False
        changed_sids.add(sid)
    return changed_sids == {"MoveOnlyTheSharedGalaEip", "ChangeOnlyKnownGalaNetworkInterfaces", "RunReadOnlyTargetHealthcheck"}


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
    # A reviewed, one-time Foundation run may retire only the two obsolete
    # validation delivery chains. EC2s, secrets, backups and logs are excluded.
    retired_slugs = {"gala-validation", "gala-validation-2"}
    retired_types = {
        "aws_ssm_document.production_deploy",
        "aws_iam_role.production_build",
        "aws_iam_role_policy.production_build",
        "aws_codebuild_project.production",
        "aws_iam_role.production_pipeline",
        "aws_iam_role_policy.production_pipeline",
        "aws_codepipeline.production",
        "aws_iam_role.production_validate",
        "aws_iam_role_policy.production_validate",
        "aws_codebuild_project.production_validate",
    }
    if slug in retired_slugs:
        allowed_retire = {
            f'{kind}["{retired_slug}"]'
            for kind in retired_types for retired_slug in retired_slugs
        }
    elif slug == "gala-smoke":
        # The Test pipeline still uses Smoke's SSM deploy document.
        allowed_retire = {
            f'{kind}["gala-smoke"]'
            for kind in retired_types - {"aws_ssm_document.production_deploy"}
        }
    else:
        allowed_retire = set()
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
        if actions == ["delete"] and address in allowed_retire:
            changed.append(f"retire-production-pipeline {address}")
            continue
        if actions == ["create"] and (
            address.startswith(f'module.gala["{slug}"].') or address in allowed_new
        ):
            changed.append(f"create {address}")
            continue
        if actions == ["update"] and safe_gala_list_prefix_update(item["change"], address):
            changed.append(f"allow-own-backup-restore {address}")
            continue
        if actions == ["update"] and (
            allowed_updates.fullmatch(address) or address == 'aws_iam_role_policy.foundation_pipeline[0]'
        ):
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
        if actions == ["update"] and (
            production_project.fullmatch(address) or address == 'aws_codebuild_project.foundation_finalize[0]'
        ):
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
                    kind = (
                        "update-foundation-finalize-buildspec"
                        if address == 'aws_codebuild_project.foundation_finalize[0]'
                        else "update-production-buildspec"
                    )
                    changed.append(f"{kind} {address}")
                    continue
        raise ValueError(f"Foundation refuses {actions} on {address}")
    return changed


def has_unknown(value: object) -> bool:
    if isinstance(value, dict):
        return any(has_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(has_unknown(item) for item in value)
    return value is True


def safe_gala_list_prefix_update(change: dict[str, object], address: str) -> bool:
    match = re.fullmatch(r'module\.gala\["([a-z0-9][a-z0-9-]{1,62})"\]\.aws_iam_role_policy\.runtime', address)
    if not match:
        return False
    gala_slug = match.group(1)
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
    if not isinstance(old_policy, dict) or not isinstance(new_policy, dict):
        return False
    if {k: v for k, v in old_policy.items() if k != "Statement"} != {k: v for k, v in new_policy.items() if k != "Statement"}:
        return False
    old_statements = old_policy.get("Statement")
    new_statements = new_policy.get("Statement")
    if not isinstance(old_statements, list) or not isinstance(new_statements, list) or len(old_statements) != len(new_statements):
        return False
    changed_sids: set[str] = set()
    expected_prefixes = {
        "ListBackupBucketOnly": f"galas/{gala_slug}/",
        "ListReleaseBucketOnly": f"releases/{gala_slug}/",
    }
    for prior, later in zip(old_statements, new_statements):
        if prior == later:
            continue
        if not isinstance(prior, dict) or not isinstance(later, dict):
            return False
        sid = prior.get("Sid")
        if not isinstance(sid, str):
            return False
        prefix = expected_prefixes.get(sid)
        if prefix is None:
            return False
        expected = copy.deepcopy(prior)
        try:
            old_prefix = expected["Condition"]["StringLike"]["s3:prefix"]
        except (KeyError, TypeError):
            return False
        if old_prefix != prefix:
            return False
        expected["Condition"]["StringLike"]["s3:prefix"] = prefix + "*"
        if later != expected:
            return False
        changed_sids.add(sid)
    return changed_sids == set(expected_prefixes)


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
    plan = json.loads(args.plan_json.read_text(encoding="utf-8"))
    phase = RETIREMENT_OPERATIONS.get(os.environ.get("GALA_NAME", ""))
    verification_phase = VERIFICATION_RETIREMENT_OPERATIONS.get(os.environ.get("GALA_NAME", ""))
    first_run_phase = FIRST_RUN_RETIREMENT_OPERATIONS.get(os.environ.get("GALA_NAME", ""))
    if phase:
        if args.slug != "gala-validation":
            raise ValueError("validation retirement requires the exact validation slug")
        changed = verify_validation_retirement_plan(plan, phase)
    elif verification_phase:
        if args.slug != VERIFICATION_SLUG:
            raise ValueError("temporary Gala retirement requires the exact verification slug")
        changed = verify_verification_retirement_plan(plan, verification_phase)
    elif first_run_phase:
        if args.slug != FIRST_RUN_SLUG:
            raise ValueError("first-run retirement requires the exact temporary slug")
        changed = verify_verification_retirement_plan(plan, first_run_phase, slug=FIRST_RUN_SLUG)
    else:
        changed = verify(plan, args.slug)
    print(f"Foundation plan accepted: {len(changed)} resource changes")
    for change in changed:
        print(change)


if __name__ == "__main__":
    main()
