"""Regression checks for retrying the pinned upstream cashless installer."""

import ast
import os
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


INSTALL = Path(__file__).resolve().parents[1] / "Laboutik" / "install.py"


def install_method(name, config):
    tree = ast.parse(INSTALL.read_text())
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    method.decorator_list = []
    scope = {
        "Configuration": types.SimpleNamespace(get_solo=lambda: config),
        "logger": Mock(),
        "os": os,
        "requests": Mock(),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(INSTALL), "exec"), scope)
    return scope[name], scope


class LaboutikRetryTests(unittest.TestCase):
    def test_existing_lespass_pairing_skips_single_use_endpoint(self):
        config = types.SimpleNamespace(
            string_connect="existing",
            key_billetterie=object(),
            billetterie_url="https://galas-am-aix.rezal.fr/",
        )
        method, scope = install_method("_lespass_handshake", config)
        with patch.dict(os.environ, LESPASS_TENANT_URL=config.billetterie_url):
            method(object())
        scope["requests"].post.assert_not_called()

    def test_existing_fedow_pairing_skips_recreation(self):
        config = types.SimpleNamespace(
            can_fedow=lambda: True,
            fedow_domain="https://fedow.galas-am-aix.rezal.fr/",
        )
        method, scope = install_method("_fedow_handshake", config)
        with patch.dict(os.environ, FEDOW_URL=config.fedow_domain):
            method(object())
        scope["requests"].get.assert_not_called()

    def test_paired_database_cannot_be_silently_retargeted(self):
        config = types.SimpleNamespace(
            string_connect="existing",
            billetterie_url="https://old.example/",
            fedow_domain="https://fedow.example/",
            can_fedow=lambda: False,
        )
        method, _ = install_method("_base_config", config)
        operator = types.SimpleNamespace(admin_email="admin@example.com")
        with patch.dict(os.environ, LESPASS_TENANT_URL="https://new.example/", FEDOW_URL=config.fedow_domain):
            with self.assertRaisesRegex(Exception, "another URL"):
                method(operator, {})


if __name__ == "__main__":
    unittest.main()
