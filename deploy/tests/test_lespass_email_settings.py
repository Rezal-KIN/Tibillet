"""Regression tests for the SMTP flags supplied by the Gala runtime."""

import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch


SETTINGS = Path(__file__).resolve().parents[2] / "TiBillet/settings.py"


class LespassEmailSettingsTests(unittest.TestCase):
    def flags(self, **environment):
        tree = ast.parse(SETTINGS.read_text(encoding="utf-8"))
        assignments = [
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id in {"EMAIL_USE_TLS", "EMAIL_USE_SSL"}
                for target in node.targets
            )
        ]
        self.assertEqual(len(assignments), 2)
        namespace = {"os": os}
        with patch.dict(os.environ, environment, clear=True):
            exec(compile(ast.Module(body=assignments, type_ignores=[]), str(SETTINGS), "exec"), namespace)
        return namespace["EMAIL_USE_TLS"], namespace["EMAIL_USE_SSL"]

    def test_gala_starttls_does_not_enable_ssl_from_string_zero(self):
        self.assertEqual(self.flags(EMAIL_USE_TLS="1", EMAIL_USE_SSL="0"), (True, False))

    def test_tls_without_ssl_flag_disables_legacy_ssl_default(self):
        self.assertEqual(self.flags(EMAIL_USE_TLS="1"), (True, False))

    def test_legacy_ssl_default_and_explicit_ssl(self):
        self.assertEqual(self.flags(), (False, True))
        self.assertEqual(self.flags(EMAIL_USE_TLS="0", EMAIL_USE_SSL="1"), (False, True))


if __name__ == "__main__":
    unittest.main()
