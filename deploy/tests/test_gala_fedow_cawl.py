"""A CAWL deployment must not require an unrelated Stripe credential."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch as environment

spec = importlib.util.spec_from_file_location(
    "patch_fedow_cawl", Path(__file__).resolve().parents[1] / "estia/gala-test/patch-fedow-cawl.py"
)
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)


class FedowCawlGuardTests(unittest.TestCase):
    def accepts(self, provider, debug=False, stripe_key=None):
        guard = "if not STRIPE_KEY_TEST and not STRIPE_KEY and not DEBUG:"
        code = overlay.patch(guard + "\n    raise ValueError('Stripe required')\n", guard)
        with environment.dict(os.environ, {"PAYMENT_PROVIDER": provider}, clear=True):
            exec(code, {"os": os, "STRIPE_KEY_TEST": None, "STRIPE_KEY": stripe_key, "DEBUG": debug})

    def test_cawl_without_stripe_works_with_debug_disabled(self):
        self.accepts("cawl")

    def test_stripe_still_requires_its_key(self):
        with self.assertRaises(ValueError):
            self.accepts("stripe")

    def test_other_existing_stripe_and_debug_cases_remain_valid(self):
        self.accepts("stripe", stripe_key="test-placeholder")
        self.accepts("stripe", debug=True)

    def test_unknown_native_source_is_rejected(self):
        with self.assertRaises(ValueError):
            overlay.patch("different source", "reviewed guard:")


if __name__ == "__main__":
    unittest.main()
