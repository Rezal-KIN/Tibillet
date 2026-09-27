"""Exercise the Smoke card setup with Laboutik Django 2.2 shell semantics."""

import io
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "runtime" / "create-qr-smoke-card.py"


class QrSmokeCardScriptTests(unittest.TestCase):
    def run_shell(self, status_code):
        config = object()
        post = Mock(return_value=types.SimpleNamespace(status_code=status_code))
        modules = {
            "APIcashless": types.ModuleType("APIcashless"),
            "APIcashless.models": types.ModuleType("APIcashless.models"),
            "fedow_connect": types.ModuleType("fedow_connect"),
            "fedow_connect.fedow_api": types.ModuleType("fedow_connect.fedow_api"),
        }
        modules["APIcashless.models"].Configuration = types.SimpleNamespace(get_solo=lambda: config)
        modules["fedow_connect.fedow_api"]._post = post
        environment = {
            "QR_SMOKE_TAG_ID": "A1B2C3D4",
            "QR_SMOKE_TAG_UUID": "97e2992f-b5fa-46af-93bb-248955d4742d",
            "QR_SMOKE_CARD_UUID": "5b8b935c-f07f-424c-9011-b3df3f29e905",
            "QR_SMOKE_CARD_NUMBER": "1234ABCD",
        }

        def old_django_shell():
            # Django 2.2 executes stdin inside Command.handle without passing
            # a globals dict; imports are therefore local to this frame.
            exec(SCRIPT.read_text(encoding="utf-8"))

        with patch.dict(sys.modules, modules), patch.dict(os.environ, environment), redirect_stdout(io.StringIO()):
            if status_code == 201:
                old_django_shell()
            else:
                with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                    old_django_shell()
        return post, config, environment

    def test_signed_card_create_works_in_old_django_shell(self):
        post, config, environment = self.run_shell(201)
        post.assert_called_once()
        self.assertIs(post.call_args.args[0], config)
        self.assertEqual(post.call_args.args[1], "card")
        self.assertEqual(post.call_args.args[2][0]["qrcode_uuid"], environment["QR_SMOKE_CARD_UUID"])

    def test_card_create_error_is_not_ignored(self):
        self.run_shell(403)


if __name__ == "__main__":
    unittest.main()
