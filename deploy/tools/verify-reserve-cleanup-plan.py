#!/usr/bin/env python3
"""Check the exact three user-authorized test reserves before local Terraform apply."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

TARGETS = {
    "gala-premier-lancement-2026-10-05": ("i-00cb72994b875e92d", "vol-0053762fa43578bd8"),
    "gala-import-cartes-2026-10-07": ("i-06c4a26b49ac45afa", "vol-049d0497923a9595f"),
    "gala-images-csv-2026-10-08": ("i-0824730d4d46b3673", "vol-05d95af2e35360299"),
}
MODULE_KINDS = {
    "aws_instance.retirable[0]", "aws_iam_role.instance",
    "aws_iam_role_policy_attachment.ssm", "aws_iam_role_policy.runtime",
    "aws_iam_instance_profile.instance", "aws_security_group.runtime",
}
DELIVERY_KINDS = {
    "aws_ssm_document.production_deploy", "aws_cloudwatch_log_group.production_deploy",
    "aws_cloudwatch_log_group.production_validate", "aws_iam_role.production_build",
    "aws_iam_role.production_pipeline", "aws_iam_role.production_validate",
    "aws_iam_role_policy.production_build", "aws_iam_role_policy.production_pipeline",
    "aws_iam_role_policy.production_validate", "aws_codebuild_project.production",
    "aws_codebuild_project.production_validate", "aws_codepipeline.production",
}
spec = importlib.util.spec_from_file_location("foundation_plan", Path(__file__).with_name("verify-foundation-plan.py"))
foundation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(foundation)


def verify(plan: dict, phase: str) -> list[str]:
    if phase not in {"prepare", "purge"}:
        raise ValueError("unknown reserve cleanup phase")
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ValueError("missing Terraform resource changes")
    allowed = {
        *(f'module.gala["{slug}"].{kind}' for slug in TARGETS for kind in MODULE_KINDS),
        *(f'{kind}["{slug}"]' for slug in TARGETS for kind in DELIVERY_KINDS),
    }
    instances = {}
    removed_arns = set()
    for item in changes:
        address = item.get("address", "")
        for slug, (instance, volume) in TARGETS.items():
            if address != f'module.gala["{slug}"].aws_instance.retirable[0]':
                continue
            before = item.get("change", {}).get("before", {})
            blocks = before.get("root_block_device", [])
            if (before.get("id") != instance or len(blocks) != 1
                    or blocks[0].get("volume_id") != volume):
                raise ValueError("reserve EC2 or root volume identity changed")
            instances[slug] = item
            removed_arns.update({
                f"arn:aws:ec2:eu-west-3:318629836660:instance/{instance}",
                f"arn:aws:ec2:eu-west-3:318629836660:network-interface/{before['primary_network_interface_id']}",
            })
            removed_arns.update(f"arn:aws:ec2:eu-west-3:318629836660:security-group/{group}"
                                for group in before.get("vpc_security_group_ids", []))
    if set(instances) != set(TARGETS):
        raise ValueError("plan must contain all three exact reserve EC2s")
    if phase == "prepare":
        return foundation.verify_validation_retirement_plan(plan, phase, targets=tuple(TARGETS))

    accepted = []
    for item in changes:
        address = item.get("address", "")
        change = item.get("change", {})
        actions = change.get("actions")
        if actions == ["no-op"] or (item.get("mode") == "data" and actions == ["read"]):
            continue
        if actions == ["delete"] and address in allowed and isinstance(change.get("before"), dict) and change.get("after") is None:
            if address.endswith(".aws_instance.retirable[0]"):
                before = change["before"]
                if before.get("disable_api_termination") is not False or before["root_block_device"][0].get("delete_on_termination") is not True:
                    raise ValueError("reserve EC2 has not been prepared")
            accepted.append(address)
        elif (actions == ["update"] and address in {"aws_iam_role_policy.test_deploy[0]", "aws_iam_role_policy.test_cawl_deploy[0]"}
              and foundation.safe_computed_policy_refresh(change)):
            accepted.append(address)
        elif actions == ["update"] and address == 'aws_iam_role_policy.active_switch_build["apply"]':
            before, after = change.get("before", {}), change.get("after", {})
            if ({k: v for k, v in before.items() if k != "policy"} != {k: v for k, v in after.items() if k != "policy"}
                    or foundation.has_unknown(change.get("after_unknown", {}))):
                raise ValueError("active switch policy identity changed")
            old, new = json.loads(before["policy"]), json.loads(after["policy"])
            if {k: v for k, v in old.items() if k != "Statement"} != {k: v for k, v in new.items() if k != "Statement"}:
                raise ValueError("active switch policy metadata changed")
            if len(old["Statement"]) != len(new["Statement"]):
                raise ValueError("active switch policy statements changed")
            for prior, later in zip(old["Statement"], new["Statement"]):
                if prior == later:
                    continue
                if prior.get("Sid") not in {"MoveOnlyTheSharedGalaEip", "ChangeOnlyKnownGalaNetworkInterfaces", "ReferenceOnlyKnownGalaSecurityGroups", "RunReadOnlyTargetHealthcheck"}:
                    raise ValueError("unrelated active switch permission changed")
                if {k: v for k, v in prior.items() if k != "Resource"} != {k: v for k, v in later.items() if k != "Resource"}:
                    raise ValueError("active switch permission changed")
                expected = [r for r in prior["Resource"] if r not in removed_arns]
                if later["Resource"] != expected:
                    raise ValueError("active switch resource removal exceeds reserves")
            accepted.append(address)
        else:
            raise ValueError(f"reserve cleanup refuses {actions} on {address}")
    return accepted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--phase", required=True, choices=("prepare", "purge"))
    args = parser.parse_args()
    accepted = verify(json.loads(args.plan.read_text()), args.phase)
    print(f"Reserve cleanup plan accepted: {len(accepted)} changes")
    for address in accepted:
        print(address)
