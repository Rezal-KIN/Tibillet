from __future__ import annotations

import importlib.util
import json
import copy
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
    def test_only_own_nested_backup_and_release_listing_updates_are_allowed(self) -> None:
        def update(slug: str) -> dict[str, object]:
            statements = [
                {"Sid": "ReadOnlyOwnRuntimeSecrets", "Effect": "Allow",
                 "Action": "secretsmanager:GetSecretValue", "Resource": "same-secret"},
                {"Sid": "ListBackupBucketOnly", "Effect": "Allow", "Action": "s3:ListBucket",
                 "Resource": "same-bucket", "Condition": {"StringLike": {"s3:prefix": f"galas/{slug}/"}}},
                {"Sid": "ListReleaseBucketOnly", "Effect": "Allow", "Action": "s3:ListBucket",
                 "Resource": "same-bucket", "Condition": {"StringLike": {"s3:prefix": f"releases/{slug}/"}}},
            ]
            later = copy.deepcopy(statements)
            for statement in later[1:]:
                statement["Condition"]["StringLike"]["s3:prefix"] += "*"
            return {
                "address": f'module.gala["{slug}"].aws_iam_role_policy.runtime',
                "change": {"actions": ["update"], "after_unknown": {},
                           "before": {"id": "same", "policy": json.dumps({"Version": "2012-10-17", "Statement": statements})},
                           "after": {"id": "same", "policy": json.dumps({"Version": "2012-10-17", "Statement": later})}},
            }

        plan = {"resource_changes": [update("gala-am-aix"), update("gala-verification")]}
        self.assertEqual(len(module.verify(plan, "gala-verification")), 2)
        for mutated in (
            lambda item: item["change"]["after"].update(id="different"),
            lambda item: item["change"].update(after_unknown={"policy": True}),
            lambda item: item["change"]["after"].update(policy=json.dumps({
                "Version": "2012-10-17", "Statement": [
                    {**statement, "Resource": "*"} if statement["Sid"] == "ListBackupBucketOnly" else statement
                    for statement in json.loads(item["change"]["after"]["policy"])["Statement"]
                ],
            })),
            lambda item: item["change"]["after"].update(policy=item["change"]["before"]["policy"]),
        ):
            bad = copy.deepcopy(plan)
            mutated(bad["resource_changes"][0])
            with self.assertRaises(ValueError):
                module.verify(bad, "gala-verification")

    def test_validation_retirement_requires_two_exact_phases(self) -> None:
        def instance(slug: str, phase: str) -> dict[str, object]:
            before = {
                "id": "i-0123456789abcdef0",
                "primary_network_interface_id": "eni-0123456789abcdef0",
                "disable_api_termination": phase == "prepare",
                "tags": {"Project": "tibillet-gala-paris", "Gala": slug, "ManagedBy": "terraform"},
                "root_block_device": [{"volume_size": 40, "delete_on_termination": phase != "prepare"}],
            }
            item = {
                "address": f'module.gala["{slug}"].aws_instance.retirable[0]',
                "change": {"actions": ["delete"] if phase == "retire" else ["update"],
                           "before": before, "after": None, "after_unknown": {}},
            }
            if phase == "prepare":
                after = copy.deepcopy(before)
                after["disable_api_termination"] = False
                after["root_block_device"][0]["delete_on_termination"] = True
                item["previous_address"] = f'module.gala["{slug}"].aws_instance.runtime[0]'
                item["change"]["after"] = after
            return item

        for phase in ("prepare", "retire"):
            plan = {"resource_changes": [instance(slug, phase)
                                         for slug in module.VALIDATION_SLUGS]}
            self.assertEqual(len(module.verify_validation_retirement_plan(plan, phase)), 2)
            bad = copy.deepcopy(plan)
            bad["resource_changes"][0]["change"]["before"]["tags"]["Gala"] = "gala-am-aix"
            with self.assertRaises(ValueError):
                module.verify_validation_retirement_plan(bad, phase)
            bad = copy.deepcopy(plan)
            bad["resource_changes"].append(change('module.gala["gala-am-aix"].aws_instance.runtime[0]', ["delete"]))
            with self.assertRaises(ValueError):
                module.verify_validation_retirement_plan(bad, phase)
        premature = {"resource_changes": [instance("gala-validation", "prepare")]}
        premature["resource_changes"][0]["change"]["actions"] = ["delete"]
        premature["resource_changes"][0]["change"]["after"] = None
        with self.assertRaises(ValueError):
            module.verify_validation_retirement_plan(premature, "retire")

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
            f"retire-production-pipeline {pipeline}",
            f"retire-production-pipeline {build}",
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

    def test_smoke_pipeline_retirement_preserves_test_document(self) -> None:
        pipeline = 'aws_codepipeline.production["gala-smoke"]'
        build = 'aws_codebuild_project.production_validate["gala-smoke"]'
        self.assertEqual(module.verify({"resource_changes": [
            change(pipeline, ["delete"]), change(build, ["delete"]),
        ]}, "gala-smoke"), [
            f"retire-production-pipeline {pipeline}",
            f"retire-production-pipeline {build}",
        ])
        for forbidden in (
            'aws_ssm_document.production_deploy["gala-smoke"]',
            'module.gala["gala-smoke"].aws_instance.runtime[0]',
            'aws_codepipeline.test[0]',
            'aws_codepipeline.production["gala-am-aix"]',
        ):
            with self.subTest(address=forbidden), self.assertRaises(ValueError):
                module.verify({"resource_changes": [change(forbidden, ["delete"])]}, "gala-smoke")


if __name__ == "__main__":
    unittest.main()
