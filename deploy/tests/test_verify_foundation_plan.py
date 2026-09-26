from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "verify_foundation_plan",
    Path(__file__).resolve().parents[1] / "tools/verify-foundation-plan.py",
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def change(address: str, actions: list[str]) -> dict[str, object]:
    return {"address": address, "change": {"actions": actions}}


class FoundationPlanTests(unittest.TestCase):
    def test_accepts_only_managed_security_group_permission_addition(self) -> None:
        address = 'aws_iam_role_policy.active_switch_build["apply"]'
        existing = {"Sid": "Existing", "Effect": "Allow", "Action": "ec2:DescribeInstances", "Resource": "*"}
        added = {
            "Sid": "ReferenceOnlyKnownGalaSecurityGroups", "Effect": "Allow",
            "Action": "ec2:ModifyNetworkInterfaceAttribute",
            "Resource": [
                "arn:aws:ec2:eu-west-3:318629836660:security-group/sg-08328acbe9b056521",
                "arn:aws:ec2:eu-west-3:318629836660:security-group/sg-0de7c48b099d4caaa",
            ],
        }
        before = {"id": "same", "policy": json.dumps({"Version": "2012-10-17", "Statement": [existing]})}
        after = {"id": "same", "policy": json.dumps({"Version": "2012-10-17", "Statement": [existing, added]})}
        update = {"address": address, "change": {
            "actions": ["update"], "before": before, "after": after, "after_unknown": {},
        }}
        self.assertEqual(module.verify({"resource_changes": [update]}, "gala-am-aix"),
                         [f"add-managed-gala-group-permission {address}"])
        for invalid in (
            {**added, "Action": "ec2:*"},
            {**added, "Resource": ["*"]},
            {**added, "Resource": ["arn:aws:ec2:eu-west-3:318629836660:security-group/sg-08328acbe9b056521"]},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                changed_after = {**after, "policy": json.dumps({
                    "Version": "2012-10-17", "Statement": [existing, invalid],
                })}
                module.verify({"resource_changes": [{**update, "change": {
                    **update["change"], "after": changed_after,
                }}]}, "gala-am-aix")

    def test_accepts_only_production_buildspec_refresh(self) -> None:
        address = 'aws_codebuild_project.production["gala-am-aix"]'
        before = {
            "name": "gala-am-aix-build", "service_role": "same-role",
            "source": [{"type": "CODEPIPELINE", "buildspec": "old"}],
        }
        after = {**before, "source": [{"type": "CODEPIPELINE", "buildspec": "new"}]}
        update = {"address": address, "change": {
            "actions": ["update"], "before": before, "after": after, "after_unknown": {},
        }}
        self.assertEqual(module.verify({"resource_changes": [update]}, "gala-am-aix"),
                         [f"update-production-buildspec {address}"])
        for invalid_after, unknown in (
            ({**after, "service_role": "another-role"}, {}),
            ({**after, "source": [{"type": "NO_SOURCE", "buildspec": "new"}]}, {}),
            (after, {"environment": [{"image": True}]}),
        ):
            with self.subTest(after=invalid_after, unknown=unknown), self.assertRaises(ValueError):
                module.verify({"resource_changes": [{**update, "change": {
                    **update["change"], "after": invalid_after, "after_unknown": unknown,
                }}]}, "gala-am-aix")

    def test_accepts_only_foundation_finalize_buildspec_refresh(self) -> None:
        address = 'aws_codebuild_project.foundation_finalize[0]'
        before = {"name": "foundation-finalize", "service_role": "same-role",
                  "source": [{"type": "CODEPIPELINE", "buildspec": "old"}]}
        after = {**before, "source": [{"type": "CODEPIPELINE", "buildspec": "new"}]}
        update = {"address": address, "change": {
            "actions": ["update"], "before": before, "after": after, "after_unknown": {},
        }}
        self.assertEqual(module.verify({"resource_changes": [update]}, "gala-validation"),
                         [f"update-foundation-finalize-buildspec {address}"])
        with self.assertRaises(ValueError):
            module.verify({"resource_changes": [{**update, "change": {
                **update["change"], "after": {**after, "service_role": "other-role"},
            }}]}, "gala-validation")

    def test_accepts_only_foundation_pipeline_policy_refresh(self) -> None:
        address = 'aws_iam_role_policy.foundation_pipeline[0]'
        update = {"address": address, "change": {
            "actions": ["update"], "before": {"id": "same", "policy": "old"},
            "after": {"id": "same"}, "after_unknown": {"policy": True},
        }}
        self.assertEqual(module.verify({"resource_changes": [update]}, "gala-validation"),
                         [f"refresh-policy {address}"])
        with self.assertRaises(ValueError):
            module.verify({"resource_changes": [{**update, "change": {
                **update["change"], "after": {"id": "different"},
            }}]}, "gala-validation")

    def test_accepts_only_requested_gala_and_switch_policy_update(self) -> None:
        plan = {"resource_changes": [
            {"mode": "data", **change('data.aws_iam_policy_document.active_switch_build["apply"]', ["read"])},
            change('module.gala["gala-validation"].aws_instance.runtime[0]', ["create"]),
            change('aws_codepipeline.production["gala-validation"]', ["create"]),
            {"address": 'aws_iam_role_policy.active_switch_build["apply"]', "change": {
                "actions": ["update"], "before": {"id": "same", "policy": "old"},
                "after": {"id": "same"}, "after_unknown": {"policy": True},
            }},
            change('module.gala["gala-smoke"].aws_instance.runtime[0]', ["no-op"]),
        ]}
        self.assertEqual(len(module.verify(plan, "gala-validation")), 3)

    def test_rejects_replacement_or_another_gala(self) -> None:
        for item in (
            change('module.gala["gala-validation"].aws_instance.runtime[0]', ["delete", "create"]),
            change('module.gala["gala-am-aix"].aws_instance.runtime[0]', ["update"]),
            change('aws_codepipeline.foundation[0]', ["update"]),
        ):
            with self.subTest(item=item), self.assertRaises(ValueError):
                module.verify({"resource_changes": [item]}, "gala-validation")

    def test_validation_pipeline_retirement_preserves_hosts_and_logs(self) -> None:
        pipeline = 'aws_codepipeline.production["gala-validation"]'
        build = 'aws_codebuild_project.production_validate["gala-validation-2"]'
        self.assertEqual(module.verify({"resource_changes": [
            change(pipeline, ["delete"]), change(build, ["delete"]),
        ]}, "gala-validation"), [
            f"retire-validation-pipeline {pipeline}",
            f"retire-validation-pipeline {build}",
        ])
        for forbidden in (
            'module.gala["gala-validation"].aws_instance.runtime[0]',
            'aws_cloudwatch_log_group.production_validate["gala-validation"]',
            'aws_secretsmanager_secret.gala["gala-validation"]',
            'aws_codepipeline.production["gala-am-aix"]',
            'aws_codepipeline.production["gala-smoke"]',
        ):
            with self.subTest(address=forbidden), self.assertRaises(ValueError):
                module.verify({"resource_changes": [change(forbidden, ["delete"])]}, "gala-validation")
        with self.assertRaises(ValueError):
            module.verify({"resource_changes": [change(pipeline, ["delete"])]}, "gala-am-aix")


if __name__ == "__main__":
    unittest.main()
