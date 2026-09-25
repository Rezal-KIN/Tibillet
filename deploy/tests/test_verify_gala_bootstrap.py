from __future__ import annotations

import importlib.util
import json
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "verify-gala-bootstrap.py"
SPEC = importlib.util.spec_from_file_location("verify_gala_bootstrap", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class BootstrapGateTests(unittest.TestCase):
    def test_only_historical_validation_maintenance_skips_runtime_gate(self) -> None:
        unchanged = {"resource_changes": [
            {"address": 'module.gala["gala-validation"].aws_instance.runtime[0]',
             "change": {"actions": ["no-op"]}},
            {"address": 'aws_iam_role_policy.test_deploy[0]',
             "change": {"actions": ["update"]}},
        ]}
        self.assertTrue(module.is_validation_retirement(unchanged, "gala-validation"))
        self.assertFalse(module.is_validation_retirement(unchanged, "gala-am-aix"))
        changed_host = {"resource_changes": [
            {"address": 'module.gala["gala-validation"].aws_instance.runtime[0]',
             "change": {"actions": ["create"]}},
        ]}
        self.assertFalse(module.is_validation_retirement(changed_host, "gala-validation"))
        with self.assertRaises(ValueError):
            module.is_validation_retirement({}, "gala-validation")

    def test_selects_only_exact_tagged_instance(self) -> None:
        instance = {
            "InstanceId": "i-0123456789abcdef0",
            "Tags": [
                {"Key": "Project", "Value": "tibillet-gala-paris"},
                {"Key": "Gala", "Value": "gala-validation"},
                {"Key": "ManagedBy", "Value": "terraform"},
            ],
        }
        with patch.object(module, "aws", return_value={"Reservations": [{"Instances": [instance]}]}):
            self.assertEqual(module.selected_instance("tibillet-gala-paris", "gala-validation"), instance["InstanceId"])

        with patch.object(module, "aws", return_value={"Reservations": [{"Instances": [instance, instance]}]}):
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                module.selected_instance("tibillet-gala-paris", "gala-validation")

    def test_failed_cloud_init_command_fails_foundation(self) -> None:
        responses = [
            {"Command": {"CommandId": "command-1"}},
            {"Status": "Failed"},
        ]
        with patch.object(module, "aws", side_effect=responses) as aws:
            with self.assertRaisesRegex(RuntimeError, "bootstrap check failed"):
                module.verify_command("i-0123456789abcdef0", "gala-validation")
        parameters = aws.call_args_list[0].args
        self.assertIn("cloud-init status --wait", " ".join(parameters))

    def test_existing_catalog_entry_skips_only_historical_cloud_init(self) -> None:
        catalog = {"version": 1, "galas": {"gala-am-aix": {}}}
        with patch.dict(module.os.environ, {"FOUNDATION_CATALOG_URI":
                     "s3://gala-backups/foundation-inputs/galas.json"}), \
             patch.object(module.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(catalog))):
            self.assertTrue(module.previously_registered("gala-am-aix"))
            self.assertFalse(module.previously_registered("gala-new"))

        responses = [{"Command": {"CommandId": "command-2"}}, {"Status": "Success"}]
        with patch.object(module, "aws", side_effect=responses) as aws:
            module.verify_command("i-0123456789abcdef0", "gala-am-aix", require_clean_cloud_init=False)
        parameters = " ".join(aws.call_args_list[0].args)
        self.assertNotIn("cloud-init status --wait", parameters)
        self.assertIn("systemctl is-enabled", parameters)
        self.assertIn("test -f /etc/tibillet-gala/gala-am-aix.conf", parameters)


if __name__ == "__main__":
    unittest.main()
