"""Safety checks must stop before reload; read-only mode must never stage a file."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "estia_websockets", Path(__file__).resolve().parents[1] /
    "estia/gala-test/activer-websockets-estia.py")
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


class EstiaChecksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.folder = root / "backup"
        self.folder.mkdir()
        available = root / "sites-available"
        available.mkdir()
        enabled = root / "sites-enabled"
        enabled.mkdir()
        self.target = available / "ours.conf"
        self.link = enabled / "ours.conf"
        self.original = b"        proxy_http_version 1.1;\n" * 2
        self.target.write_bytes(self.original)
        self.link.symlink_to(self.target)
        self.reference = self.folder / "https-caisse.conf"
        self.reference.write_bytes(self.original)
        self.protected = root / "nginx.conf"
        self.protected.write_text("# protected\n")
        before = {"files": {str(self.protected): {
            "target": str(self.protected.resolve()),
            "sha256": hashlib.sha256(self.protected.read_bytes()).hexdigest()}}, "enabled": {}}
        (self.folder / "avant.json").write_text(json.dumps(before))
        self.loaded = "# configuration file %s:\n# configuration file %s:\n" % (self.protected, self.link)
        self.sites = {"https://" + host: {"status": 200} for host in (
            "gala-test.rezal.fr", "cashless.gala-test.rezal.fr", "fedow.gala-test.rezal.fr")}
        self.sites["https://hello.rezal.fr"] = {
            "status": 200, "body_sha256": "body", "certificate": "cert"}
        self.calls = []
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        for name, value in (("FOLDER", self.folder), ("TARGET", self.target), ("LINK", self.link)):
            stack.enter_context(patch.object(script, name, value))
        stack.enter_context(patch.object(script.socket, "gethostname", return_value="estia"))
        stack.enter_context(patch.object(script.os, "geteuid", return_value=0))
        self.state = stack.enter_context(patch.object(script, "nginx_state", return_value=(504, {123})))
        stack.enter_context(patch.object(script, "sites_snapshot", return_value=self.sites))
        stack.enter_context(patch.object(script, "wait_for_reload"))
        stack.enter_context(patch.object(script, "websocket_check"))
        stack.enter_context(patch.object(script.subprocess, "run", side_effect=self.run_command))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def run_command(self, command, **kwargs):
        self.calls.append(command)
        return SimpleNamespace(returncode=0, stdout=self.loaded, stderr="")

    def main(self, *args):
        with patch("sys.argv", ["script"] + list(args)):
            script.main()

    def assert_no_activation(self):
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.reference.read_bytes(), self.original)
        self.assertNotIn(["systemctl", "reload", "nginx"], self.calls)

    def test_read_only_mode_never_changes_configuration_or_creates_backup(self):
        files = sorted(self.folder.iterdir())
        self.main("--verifier")
        self.assert_no_activation()
        self.assertEqual(sorted(self.folder.iterdir()), files)

    def test_changed_protected_file_stops_before_any_nginx_command(self):
        self.protected.write_text("concurrent edit")
        with self.assertRaisesRegex(RuntimeError, "fichier protege modifie"):
            self.main()
        self.assert_no_activation()
        self.assertEqual(self.calls, [])

    def test_unexpected_include_stops_before_any_write(self):
        self.loaded += "# configuration file /unexpected.conf:\n"
        with self.assertRaisesRegex(RuntimeError, "liste inattendue"):
            self.main()
        self.assert_no_activation()
        self.assertFalse((self.folder / "https-caisse-avant-websockets.conf").exists())

    def test_concurrent_reload_during_preflight_blocks_activation(self):
        self.state.side_effect = [(504, {123}), (504, {456})]
        with self.assertRaisesRegex(RuntimeError, "Etat nginx modifie"):
            self.main()
        self.assert_no_activation()

    def test_invalid_staged_configuration_restores_only_our_files_without_reload(self):
        def run(command, **kwargs):
            self.calls.append(command)
            invalid = self.target.read_bytes() != self.original
            return SimpleNamespace(returncode=int(invalid), stdout=self.loaded, stderr="invalid")
        with patch.object(script.subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "test nginx echoue"):
                self.main()
        self.assert_no_activation()
        self.assertEqual(self.protected.read_text(), "# protected\n")

    def test_post_reload_failure_never_triggers_another_global_reload(self):
        with patch.object(script, "websocket_check", side_effect=RuntimeError("handshake failed")):
            with self.assertRaisesRegex(RuntimeError, "handshake failed"):
                self.main()
        self.assertEqual(self.calls.count(["systemctl", "reload", "nginx"]), 1)
        self.assertIn(b"proxy_set_header Upgrade", self.target.read_bytes())
        self.assertEqual(self.reference.read_bytes(), self.target.read_bytes())
        self.assertEqual((self.folder / "https-caisse-avant-websockets.conf").read_bytes(), self.original)

    def test_success_preserves_other_files_and_reexecution_does_not_reload(self):
        self.main()
        self.assertEqual(self.protected.read_text(), "# protected\n")
        self.assertEqual(self.calls.count(["systemctl", "reload", "nginx"]), 1)
        self.main()
        self.assertEqual(self.calls.count(["systemctl", "reload", "nginx"]), 1)

    def test_changed_hello_body_certificate_or_status_is_reported(self):
        before = self.sites["https://hello.rezal.fr"]
        for key, value in (("status", 502), ("certificate", "changed"), ("body_sha256", "changed")):
            with self.subTest(key=key):
                after = dict(before, **{key: value})
                with self.assertRaisesRegex(RuntimeError, "hello.rezal.fr"):
                    script.compare_sites({"https://hello.rezal.fr": before}, {"https://hello.rezal.fr": after})


if __name__ == "__main__":
    unittest.main()
