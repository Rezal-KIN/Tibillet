"""Environment consolidation preserves existing keys and concurrent additions."""
import copy
import json
import unittest
from unittest.mock import patch

from test_gala_credentials import generator, renderer, STRIPE_TEST, SHARED_MAIL


def payload():
    return {
        "schema_version": 2, "environment": "dev", **{k: v for k, v in STRIPE_TEST.items() if k != "schema_version"},
        "cawl": {"mode": "test", **{k: "example" for k in ("merchant_id", "api_key_id", "api_secret", "webhook_key_id", "webhook_secret")}},
        **{k: v for k, v in SHARED_MAIL.items() if k != "schema_version"},
        "admin": {"username": "admin", "password_hash": "pbkdf2_sha256$390000$sampleSalt$" + "A" * 43 + "="},
        "galas": {"gala-smoke": generator.generated_payload(), "gala-smoke-cawl": generator.generated_payload()},
    }


class EnvironmentSecretTests(unittest.TestCase):
    def test_unified_payload_renders_identically_for_both_providers(self):
        source = payload()
        domains = ("fedow.galas-am-aix.rezal.fr", "cashless.galas-am-aix.rezal.fr", "galas-am-aix.rezal.fr")
        for slug, provider in (("gala-smoke", "stripe"), ("gala-smoke-cawl", "cawl")):
            generated, payment, mail, admin = renderer.environment_sections(source, slug, True)
            expected = renderer.assemble(source["galas"][slug], payment, SHARED_MAIL, *domains, True,
                                         admin_secret=source["admin"], require_admin=True, payment_provider=provider)
            actual = renderer.assemble(generated, payment, mail, *domains, True,
                                       admin_secret=admin, require_admin=True, payment_provider=provider)
            self.assertEqual(expected, actual)
        self.assertNotEqual(source["galas"]["gala-smoke"], source["galas"]["gala-smoke-cawl"])

    def test_environment_and_missing_gala_cannot_fall_back(self):
        source = payload()
        for slug, smoke in (("gala-smoke", False), ("gala-other", True)):
            with self.assertRaises(ValueError):
                renderer.environment_sections(source, slug, smoke)
        source["galas"]["gala-production"] = generator.generated_payload()
        with self.assertRaisesRegex(ValueError, "wrong environment"):
            renderer.environment_sections(source, "gala-smoke", True)

    def test_initializer_preserves_other_entries_when_current_changes(self):
        state = {"schema_version": 2, "environment": "prod", "galas": {"gala-existing": generator.generated_payload()}}
        original = copy.deepcopy(state["galas"])
        other = generator.generated_payload()
        calls = []

        def read(_):
            return copy.deepcopy(state), str(len(calls))

        def publish(_, version, candidate):
            calls.append(copy.deepcopy(candidate))
            if len(calls) == 1:
                state["galas"]["gala-concurrent"] = other
                return False
            state.update(candidate)
            return True

        with patch.object(generator, "read_environment", side_effect=read), patch.object(generator, "publish_environment", side_effect=publish):
            generator.initialize("prod", "gala-new")
        self.assertEqual(state["galas"]["gala-existing"], original["gala-existing"])
        self.assertEqual(state["galas"]["gala-concurrent"], other)
        self.assertIn("gala-new", state["galas"])
        self.assertEqual(len(calls), 2)

    def test_initializer_never_regenerates_a_concurrently_added_entry(self):
        existing = generator.generated_payload()
        snapshots = [({"schema_version": 2, "environment": "prod", "galas": {}}, "old"),
                     ({"schema_version": 2, "environment": "prod", "galas": {"gala-new": existing}}, "new")]
        with patch.object(generator, "read_environment", side_effect=snapshots), patch.object(generator, "publish_environment", return_value=False) as publish:
            generator.initialize("prod", "gala-new")
        self.assertEqual(publish.call_count, 1)

    def test_compare_and_swap_uses_the_observed_current_version(self):
        calls = []
        def aws(*args):
            calls.append(args)
            if args[1] == "update-secret-version-stage" and args[args.index("--version-stage") + 1] == "AWSCURRENT":
                self.assertEqual(args[args.index("--remove-from-version-id") + 1], "observed-version")
                raise RuntimeError("concurrent version")
            return "candidate"
        with patch.object(generator, "aws", side_effect=aws), patch.object(generator, "read_environment", return_value=({}, "another-version")):
            self.assertFalse(generator.publish_environment("prod", "observed-version", {"galas": {}}))
        self.assertEqual(len(calls), 3)
        self.assertIn("--version-stages", calls[0])

    def test_wrong_environment_and_oversized_payload_are_rejected_before_write(self):
        with patch.object(generator, "read_environment", return_value=({"schema_version": 2, "environment": "dev", "galas": {}}, "v")), patch.object(generator, "publish_environment") as publish:
            with self.assertRaises(RuntimeError):
                generator.initialize("dev", "gala-prod")
            publish.assert_not_called()
        with patch.object(generator, "aws") as aws:
            with self.assertRaisesRegex(RuntimeError, "size limit"):
                generator.publish_environment("prod", "old", {"value": "x" * 65536})
            aws.assert_not_called()


if __name__ == "__main__":
    unittest.main()
