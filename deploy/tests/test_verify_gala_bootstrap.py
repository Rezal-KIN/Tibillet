from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "verify-gala-bootstrap.py"
SPEC = importlib.util.spec_from_file_location("verify_gala_bootstrap", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class BootstrapGateTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
