from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
