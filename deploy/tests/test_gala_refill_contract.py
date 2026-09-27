"""The reviewed release enables and verifies the real QR refill action."""

import unittest
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[1] / "tools" / "runtime"


class GalaRefillContractTests(unittest.TestCase):
    def test_release_reconciles_refill_after_fedow_credentials(self):
        release = (RUNTIME / "deploy-release.sh").read_text(encoding="utf-8")
        self.assertLess(
            release.index("reconcile-fedow-webhook.py"),
            release.index("manage.py configure_gala_refill"),
        )
        self.assertLess(release.index("manage.py configure_gala_refill"), release.index("healthy=false"))

    def test_healthcheck_requires_visible_refill(self):
        health = (RUNTIME / "healthcheck.sh").read_text(encoding="utf-8")
        self.assertIn("manage.py configure_gala_refill --check", health)

    def test_qr_e2e_uses_actual_configuration(self):
        qr = (Path(__file__).resolve().parents[2] / "tests" / "pytest" / "test_qr_card_fedow_e2e.py")
        source = qr.read_text(encoding="utf-8")
        self.assertIn("Configuration.get_solo().show_refill_button() is True", source)
        self.assertNotIn("patch.object(Configuration, 'show_refill_button'", source)


if __name__ == "__main__":
    unittest.main()
