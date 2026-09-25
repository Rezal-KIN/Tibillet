from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "tools/switch-active-gala.py"
spec = importlib.util.spec_from_file_location("active_gala_switch", SCRIPT)
assert spec is not None and spec.loader is not None
switch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(switch)


SETTINGS = {
    "project": "tibillet-gala-paris",
    "catalog_uri": "s3://example/foundation-inputs/galas.json",
    "allocation_id": "eipalloc-0a985f5daf0f7d969",
    "public_group": "sg-0123456789abcdef0",
    "active_parameter": "/tibillet-gala-paris/active-gala",
    "public_domain": "galas-am-aix.rezal.fr",
}
PLAN = {
    "version": 1,
    "source_commit": "a" * 40,
    "target_slug": "gala-smoke",
    "target_instance_id": "i-0037b98572fccdff2",
    "target_eni": "eni-target",
    "target_groups": ["sg-target"],
    "domain": "galas-am-aix.rezal.fr",
    "current_marker": "gala-am-aix",
    "current_instance_id": "i-0801aa8a2273838aa",
    "current_eni": "eni-old",
    "current_groups": ["sg-old", "sg-0123456789abcdef0"],
    "eip_allocation_id": "eipalloc-0a985f5daf0f7d969",
    "eip_association_id": "eipassoc-old",
    "eip_public_ip": "51.44.90.200",
    "public_group": "sg-0123456789abcdef0",
    "active_parameter": "/tibillet-gala-paris/active-gala",
}


class ActiveGalaSwitchTests(unittest.TestCase):
    def test_rejects_stale_plan_before_mutation(self) -> None:
        with mock.patch.object(switch, "build_plan", return_value={**PLAN, "current_marker": "other"}), mock.patch.object(switch, "aws") as aws:
            with self.assertRaisesRegex(ValueError, "stale"):
                switch.apply_plan(PLAN, SETTINGS)
        aws.assert_not_called()

    def test_success_moves_one_eip_and_records_target(self) -> None:
        calls = []

        def fake_aws(*arguments):
            calls.append(arguments)
            if arguments[:2] == ("ec2", "describe-addresses"):
                return {"Addresses": [{"InstanceId": PLAN["target_instance_id"]}]}
            return {}

        with (
            mock.patch.object(switch, "build_plan", return_value=PLAN),
            mock.patch.object(switch, "verify_target_local"),
            mock.patch.object(switch, "restart_target_proxy") as restart,
            mock.patch.object(switch, "check_public"),
            mock.patch.object(switch, "aws", side_effect=fake_aws),
        ):
            switch.apply_plan(PLAN, SETTINGS)

        restart.assert_called_once_with(PLAN)
        self.assertTrue(any(args[:2] == ("ec2", "associate-address") and "eni-target" in args for args in calls))
        self.assertTrue(any(args[:2] == ("ssm", "put-parameter") and "gala-smoke" in args for args in calls))
        self.assertTrue(any(args[:2] == ("ec2", "modify-network-interface-attribute") and "eni-old" in args for args in calls))

    def test_public_failure_restores_previous_eip_and_groups(self) -> None:
        calls = []

        def fake_aws(*arguments):
            calls.append(arguments)
            if arguments[:2] == ("ec2", "describe-addresses"):
                return {"Addresses": [{"InstanceId": PLAN["target_instance_id"]}]}
            return {}

        with (
            mock.patch.object(switch, "build_plan", return_value=PLAN),
            mock.patch.object(switch, "verify_target_local"),
            mock.patch.object(switch, "restart_target_proxy"),
            mock.patch.object(switch, "check_public", side_effect=RuntimeError("TLS failed")),
            mock.patch.object(switch, "aws", side_effect=fake_aws),
        ):
            with self.assertRaisesRegex(RuntimeError, "restored"):
                switch.apply_plan(PLAN, SETTINGS)

        associations = [args for args in calls if args[:2] == ("ec2", "associate-address")]
        self.assertEqual(len(associations), 2)
        self.assertIn("eni-target", associations[0])
        self.assertIn("eni-old", associations[1])
        self.assertFalse(any(args[:2] == ("ssm", "put-parameter") for args in calls))

    def test_proxy_restart_uses_only_the_planned_instance(self) -> None:
        responses = [
            {"Command": {"CommandId": "command-1"}},
            {"Status": "Success"},
        ]
        with mock.patch.object(switch, "aws", side_effect=responses) as aws, \
             mock.patch.object(switch.time, "sleep"):
            switch.restart_target_proxy(PLAN)
        self.assertIn(PLAN["target_instance_id"], aws.call_args_list[0].args)
        self.assertIn("docker restart traefik", aws.call_args_list[0].args[7])


if __name__ == "__main__":
    unittest.main()
