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
    def test_image_build_keeps_role_and_only_adds_two_repository_names(self):
        env = [{'name': 'LESPASS_ECR_REPOSITORY', 'type': 'PLAINTEXT', 'value': 'tibillet-gala-paris/lespass'}]
        before = {'name': 'test', 'service_role': 'same', 'source': [{'type': 'CODEPIPELINE', 'buildspec': 'old'}],
                  'environment': [{'privileged_mode': True, 'environment_variable': env}]}
        after = copy.deepcopy(before)
        after['source'][0]['buildspec'] = 'new'
        after['environment'][0]['environment_variable'].extend([
            {'name': c.upper()+'_ECR_REPOSITORY', 'type': 'PLAINTEXT', 'value': 'tibillet-gala-paris/'+c}
            for c in ('fedow', 'laboutik')])
        change = {'before': before, 'after': after, 'after_unknown': {}}
        self.assertTrue(module.safe_application_build_project(change))
        for mutation in (lambda v: v['after'].update(service_role='admin'),
                         lambda v: v['after']['environment'][0].update(privileged_mode=False),
                         lambda v: v['after']['environment'][0]['environment_variable'][-1].update(value='other/laboutik')):
            bad = copy.deepcopy(change); mutation(bad)
            self.assertFalse(module.safe_application_build_project(bad))

    def test_image_policy_refresh_requires_actual_gala_identity(self):
        before = {'name': 'tibillet-gala-paris-gala-smoke-runtime', 'role': 'tibillet-gala-paris-gala-smoke-ec2', 'policy': '{}'}
        change = {'before': before, 'after': {**before, 'policy': None}, 'after_unknown': {'policy': True}}
        address = 'module.gala["gala-smoke"].aws_iam_role_policy.runtime'
        self.assertTrue(module.safe_image_policy_refresh(change, address))
        self.assertFalse(module.safe_image_policy_refresh(change, 'module.gala["gala-other"].aws_iam_role_policy.runtime'))
        self.assertFalse(module.safe_image_policy_refresh({**change, 'after': {**before, 'policy': '{}'}}, address))

    def test_test_pipeline_refresh_cannot_change_permissions_or_identity(self) -> None:
        address = 'aws_iam_role_policy.test_pipeline[0]'
        before = {
            "id": "test-pipeline:test-pipeline", "name": "test-pipeline",
            "role": "test-pipeline", "policy": json.dumps({
                "Version": "2012-10-17", "Statement": [{
                    "Effect": "Allow", "Action": "codebuild:StartBuild",
                    "Resource": "arn:aws:codebuild:eu-west-3:318629836660:project/test",
                }],
            }),
        }
        refresh = {"address": address, "change": {
            "actions": ["update"], "before": before,
            "after": {**before, "policy": None}, "after_unknown": {"policy": True},
        }}
        self.assertEqual(module.verify({"resource_changes": [refresh]}, "gala-new"),
                         [f"refresh-policy {address}"])
        for mutation in (
            lambda item: item["change"]["after"].update(policy='{"Statement": []}'),
            lambda item: item["change"]["after"].update(role="different-role"),
            lambda item: item["change"]["after"].update(name="different-policy"),
            lambda item: item["change"].update(after_unknown={"policy": True, "role": True}),
            lambda item: item["change"].update(after_unknown={}),
            lambda item: item["change"].update(actions=["delete"]),
            lambda item: item.update(address='aws_iam_role_policy.test_pipeline[1]'),
            lambda item: item.update(address='aws_iam_role_policy.test_build[0]'),
        ):
            bad = copy.deepcopy(refresh)
            mutation(bad)
            with self.subTest(change=bad), self.assertRaises(ValueError):
                module.verify({"resource_changes": [bad]}, "gala-new")

    def test_first_run_retirement_requires_exact_instance_and_volume(self) -> None:
        slug = module.FIRST_RUN_SLUG
        address = f'module.gala["{slug}"].aws_instance.retirable[0]'
        before = {
            "id": module.FIRST_RUN_INSTANCE_ID,
            "primary_network_interface_id": "eni-0123456789abcdef0",
            "disable_api_termination": True,
            "tags": {"Project": "tibillet-gala-paris", "Gala": slug, "ManagedBy": "terraform"},
            "root_block_device": [{"volume_id": module.FIRST_RUN_VOLUME_ID,
                                   "volume_size": 40, "delete_on_termination": False}],
        }
        after = copy.deepcopy(before)
        after["disable_api_termination"] = False
        after["root_block_device"][0]["delete_on_termination"] = True
        prepare = {"address": address,
                   "previous_address": f'module.gala["{slug}"].aws_instance.runtime[0]',
                   "change": {"actions": ["update"], "before": before, "after": after,
                              "after_unknown": {}}}
        self.assertEqual(len(module.verify_verification_retirement_plan(
            {"resource_changes": [prepare]}, "prepare", slug=slug)), 1)
        wrong = copy.deepcopy(prepare)
        wrong["change"]["before"]["root_block_device"][0]["volume_id"] = "vol-00000000000000000"
        with self.assertRaises(ValueError):
            module.verify_verification_retirement_plan(
                {"resource_changes": [wrong]}, "prepare", slug=slug)
        retire = {"address": address, "change": {"actions": ["delete"],
                  "before": after, "after": None, "after_unknown": {}}}
        pipeline = {"address": f'aws_codepipeline.production["{slug}"]',
                    "change": {"actions": ["delete"], "before": {"id": "same"}, "after": None}}
        self.assertEqual(len(module.verify_verification_retirement_plan(
            {"resource_changes": [retire, pipeline]}, "retire", slug=slug)), 2)
        with self.assertRaises(ValueError):
            module.verify_verification_retirement_plan({"resource_changes": [
                retire, change('module.gala["gala-am-aix"].aws_instance.runtime[0]', ["delete"]),
            ]}, "retire", slug=slug)

    def test_temporary_gala_retirement_targets_only_verified_ec2_and_pipeline(self) -> None:
        address = 'module.gala["gala-verification"].aws_instance.retirable[0]'
        before = {
            "id": module.VERIFICATION_INSTANCE_ID,
            "primary_network_interface_id": "eni-0123456789abcdef0",
            "disable_api_termination": True,
            "tags": {"Project": "tibillet-gala-paris", "Gala": "gala-verification", "ManagedBy": "terraform"},
            "root_block_device": [{"volume_id": module.VERIFICATION_VOLUME_ID,
                                   "volume_size": 40, "delete_on_termination": False}],
        }
        after = copy.deepcopy(before)
        after["disable_api_termination"] = False
        after["root_block_device"][0]["delete_on_termination"] = True
        prepare = {"address": address,
                   "previous_address": 'module.gala["gala-verification"].aws_instance.runtime[0]',
                   "change": {"actions": ["update"], "before": before, "after": after,
                              "after_unknown": {}}}
        self.assertEqual(len(module.verify_verification_retirement_plan(
            {"resource_changes": [prepare]}, "prepare")), 1)
        wrong = copy.deepcopy(prepare)
        wrong["change"]["before"]["id"] = "i-00000000000000000"
        with self.assertRaises(ValueError):
            module.verify_verification_retirement_plan({"resource_changes": [wrong]}, "prepare")
        with self.assertRaises(ValueError):
            module.verify_verification_retirement_plan({"resource_changes": [prepare, change(
                'module.gala["gala-am-aix"].aws_instance.runtime[0]', ["delete"])]}, "prepare")

        retire = {"address": address, "change": {"actions": ["delete"],
                  "before": after, "after": None, "after_unknown": {}}}
        pipeline = {"address": 'aws_codepipeline.production["gala-verification"]',
                    "change": {"actions": ["delete"], "before": {"id": "same"}, "after": None}}
        self.assertEqual(len(module.verify_verification_retirement_plan(
            {"resource_changes": [retire, pipeline]}, "retire")), 2)
        policy_addresses = (
            'aws_iam_role_policy.production_build["gala-am-aix"]',
            'aws_iam_role_policy.production_pipeline["gala-am-aix"]',
            'aws_iam_role_policy.test_deploy[0]',
        )
        policy_refreshes = [
            {"address": policy_address, "change": {
                "actions": ["update"],
                "before": {"id": "same", "name": "same", "policy": "old-policy"},
                "after": {"id": "same", "name": "same", "policy": None},
                "after_unknown": {"policy": True},
            }} for policy_address in policy_addresses
        ]
        self.assertEqual(len(module.verify_verification_retirement_plan(
            {"resource_changes": [retire, pipeline, *policy_refreshes]}, "retire")), 5)
        for mutation in (
            lambda item: item["change"]["after"].update(name="different"),
            lambda item: item["change"].update(after_unknown={"policy": True, "role": True}),
            lambda item: item["change"]["after"].update(policy="broader-policy"),
            lambda item: item.update(address='aws_iam_role_policy.production_build["gala-smoke"]'),
        ):
            bad = copy.deepcopy(policy_refreshes[0])
            mutation(bad)
            with self.assertRaises(ValueError):
                module.verify_verification_retirement_plan(
                    {"resource_changes": [retire, pipeline, bad]}, "retire")
        for forbidden in (
            'aws_cloudwatch_log_group.production_deploy["gala-verification"]',
            'module.gala["gala-verification"].aws_secretsmanager_secret.generated',
            'aws_codepipeline.production["gala-am-aix"]',
        ):
            with self.subTest(address=forbidden), self.assertRaises(ValueError):
                module.verify_verification_retirement_plan({"resource_changes": [
                    retire, {"address": forbidden, "change": {
                        "actions": ["delete"], "before": {"id": "same"}, "after": None,
                    }},
                ]}, "retire")

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
