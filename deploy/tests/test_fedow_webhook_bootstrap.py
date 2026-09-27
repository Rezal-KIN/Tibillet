"""The release must initialize Fedow's live webhook key on first boot."""

import ast
import hmac
import os
import types
import unittest
from pathlib import Path
from unittest.mock import patch


RUNTIME = Path(__file__).resolve().parents[1] / "tools" / "runtime"
SCRIPT = RUNTIME / "reconcile-fedow-webhook.py"


class FakeConfiguration:
    def __init__(self, initial="", test_mode=False):
        self.stripe_endpoint_secret_enc = initial or None
        self.secret = initial
        self.test_mode = test_mode
        self.writes = 0

    def get_stripe_endpoint_secret(self):
        if self.test_mode:
            return os.environ.get("STRIPE_ENDPOINT_SECRET_TEST")
        return self.secret

    def set_stripe_endpoint_secret(self, secret):
        self.secret = secret
        self.stripe_endpoint_secret_enc = "encrypted"
        self.writes += 1


def reconcile_function(config, test_mode=False):
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    method = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "reconcile")
    scope = {
        "os": os,
        "hmac": hmac,
        "settings": types.SimpleNamespace(STRIPE_TEST=test_mode),
        "Configuration": types.SimpleNamespace(get_solo=lambda: config),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(SCRIPT), "exec"), scope)
    return scope["reconcile"]


class FedowWebhookBootstrapTests(unittest.TestCase):
    def test_first_live_deployment_and_rotation_are_idempotent(self):
        config = FakeConfiguration()
        reconcile = reconcile_function(config)
        with patch.dict(os.environ, {"STRIPE_ENDPOINT_SECRET": "whsec_first"}):
            reconcile()
            reconcile()
        self.assertEqual(config.writes, 1)
        with patch.dict(os.environ, {"STRIPE_ENDPOINT_SECRET": "whsec_rotated"}):
            reconcile()
        self.assertEqual(config.writes, 2)
        self.assertEqual(config.secret, "whsec_rotated")

    def test_missing_live_secret_fails_closed(self):
        reconcile = reconcile_function(FakeConfiguration())
        with patch.dict(os.environ, {"STRIPE_ENDPOINT_SECRET": ""}):
            with self.assertRaisesRegex(RuntimeError, "missing or invalid"):
                reconcile()

    def test_smoke_uses_environment_without_database_write(self):
        config = FakeConfiguration(test_mode=True)
        reconcile = reconcile_function(config, test_mode=True)
        with patch.dict(os.environ, {"STRIPE_ENDPOINT_SECRET_TEST": "whsec_smoke"}):
            reconcile()
        self.assertEqual(config.writes, 0)

    def test_release_runs_reconciliation_before_healthcheck(self):
        release = (RUNTIME / "deploy-release.sh").read_text(encoding="utf-8")
        install = (RUNTIME / "install-runtime-contract.sh").read_text(encoding="utf-8")
        self.assertLess(release.index("reconcile-fedow-webhook.py"), release.index("healthy=false"))
        self.assertIn("reconcile-fedow-webhook.py", install)

    def test_release_migrates_without_forked_executor(self):
        release = (RUNTIME / "deploy-release.sh").read_text(encoding="utf-8")
        command = next(line for line in release.splitlines() if "poetry run python manage.py migrate_schemas'" in line)
        self.assertNotIn("--executor", command)


if __name__ == "__main__":
    unittest.main()
