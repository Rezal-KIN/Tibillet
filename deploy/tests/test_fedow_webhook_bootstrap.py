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


class FakeConnection:
    def __init__(self, column_types=None):
        self.types = column_types or {
            "stripe_endpoint_secret_enc": "character varying",
            "stripe_api_key": "character varying",
        }
        self.alterations = []
        self.ops = types.SimpleNamespace(quote_name=lambda name: f'"{name}"')

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        if sql.startswith("SELECT"):
            self.selected = list(self.types.items())
            self.params = params
        elif sql.startswith("ALTER TABLE"):
            column = next(name for name in self.types if f'"{name}"' in sql)
            self.types[column] = "text"
            self.alterations.append(column)
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return self.selected


def reconcile_function(config, test_mode=False, storage=None):
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    methods = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in {"ensure_secret_storage", "reconcile"}
    ]
    storage = storage or FakeConnection()
    scope = {
        "os": os,
        "hmac": hmac,
        "settings": types.SimpleNamespace(STRIPE_TEST=test_mode),
        "Configuration": types.SimpleNamespace(
            get_solo=lambda: config,
            _meta=types.SimpleNamespace(db_table="fedow_core_configuration"),
        ),
        "connection": storage,
    }
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(SCRIPT), "exec"), scope)
    reconcile = scope["reconcile"]
    reconcile.storage = storage
    return reconcile


class FedowWebhookBootstrapTests(unittest.TestCase):
    def test_first_live_deployment_and_rotation_are_idempotent(self):
        config = FakeConfiguration()
        reconcile = reconcile_function(config)
        with patch.dict(os.environ, {"STRIPE_ENDPOINT_SECRET": "whsec_first"}):
            reconcile()
            reconcile()
        self.assertEqual(config.writes, 1)
        self.assertEqual(set(reconcile.storage.alterations), {"stripe_endpoint_secret_enc", "stripe_api_key"})
        self.assertEqual(len(reconcile.storage.alterations), 2)
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
        self.assertEqual(len(reconcile.storage.alterations), 2)

    def test_missing_storage_column_fails_closed(self):
        storage = FakeConnection({"stripe_endpoint_secret_enc": "character varying"})
        reconcile = reconcile_function(FakeConfiguration(test_mode=True), test_mode=True, storage=storage)
        with patch.dict(os.environ, {"STRIPE_ENDPOINT_SECRET_TEST": "whsec_smoke"}):
            with self.assertRaisesRegex(RuntimeError, "columns are missing"):
                reconcile()

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
