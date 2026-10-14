"""Complete cleanup must stay confined to the three explicitly approved reserves."""
import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("reserve_cleanup", Path(__file__).parents[1] / "tools/verify-reserve-cleanup-plan.py")
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


def plan(phase):
    changes = []
    for index, (slug, (instance, volume)) in enumerate(cleanup.TARGETS.items()):
        before = {
            "id": instance, "primary_network_interface_id": f"eni-{index:017x}",
            "disable_api_termination": phase == "prepare",
            "tags": {"Project": "tibillet-gala-paris", "Gala": slug, "ManagedBy": "terraform"},
            "root_block_device": [{"volume_id": volume, "volume_size": 40,
                                   "delete_on_termination": phase != "prepare"}],
        }
        after = copy.deepcopy(before) if phase == "prepare" else None
        if after:
            after["disable_api_termination"] = False
            after["root_block_device"][0]["delete_on_termination"] = True
        changes.append({"address": f'module.gala["{slug}"].aws_instance.retirable[0]',
                        "change": {"actions": ["update" if after else "delete"],
                                   "before": before, "after": after, "after_unknown": {}}})
    return {"resource_changes": changes}


class ReserveCleanupTests(unittest.TestCase):
    def test_missing_or_changed_target_is_rejected(self):
        for phase in ("prepare", "purge"):
            valid = plan(phase)
            self.assertEqual(len(cleanup.verify(valid, phase)), 3)
            invalid = copy.deepcopy(valid)
            invalid["resource_changes"].pop()
            with self.assertRaises(ValueError):
                cleanup.verify(invalid, phase)
            invalid = copy.deepcopy(valid)
            invalid["resource_changes"][0]["change"]["before"]["root_block_device"][0]["volume_id"] = "vol-00000000000000000"
            with self.assertRaises(ValueError):
                cleanup.verify(invalid, phase)

    def test_shared_resources_and_other_galas_are_rejected(self):
        for address in ('module.gala["gala-smoke"].aws_instance.retirable[0]',
                        'aws_s3_bucket.backups[0]', 'aws_ecr_repository.lespass[0]',
                        'aws_codepipeline.test[0]'):
            invalid = plan("purge")
            invalid["resource_changes"].append({"address": address,
                "change": {"actions": ["delete"], "before": {}, "after": None}})
            with self.assertRaises(ValueError):
                cleanup.verify(invalid, "purge")

    def test_purge_refuses_unprepared_volume_or_replacement(self):
        invalid = plan("purge")
        invalid["resource_changes"][0]["change"]["before"]["root_block_device"][0]["delete_on_termination"] = False
        with self.assertRaises(ValueError):
            cleanup.verify(invalid, "purge")
        invalid = plan("purge")
        invalid["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
        with self.assertRaises(ValueError):
            cleanup.verify(invalid, "purge")


if __name__ == "__main__":
    unittest.main()
