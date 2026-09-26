from __future__ import annotations

import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_module("gala_secret_generator", ROOT / "tools/initialize-gala-credentials.py")
renderer = load_module("gala_env_renderer", ROOT / "tools/runtime/materialize-runtime-env.py")


STRIPE_TEST = {
    "schema_version": 1,
    "stripe": {
        "mode": "test",
        "secret_key": "sk_test_example",
        "publishable_key": "pk_test_example",
        "fedow_webhook_secret": "whsec_example",
    },
}
SHARED_MAIL = {
    "schema_version": 1,
    "mail": {
        "host": "smtp.example.fr",
        "port": 587,
        "username": "mail-user",
        "password": "sample$#'password",
        "from": "contact@example.fr",
        "admin_email": "admin@example.fr",
    },
    "test_recipient": "smoke@example.fr",
    "site": {
        "lespass_domain": "galas-am-aix.rezal.fr",
        "fedow_domain": "fedow.galas-am-aix.rezal.fr",
        "laboutik_domain": "cashless.galas-am-aix.rezal.fr",
        "public_name": "Gala Example",
        "tenant_subdomain": "festival",
        "meta_subdomain": "agenda",
    },
}


class GeneratedGalaSecretTests(unittest.TestCase):
    def test_laboutik_bootstrap_uses_this_galas_local_services(self) -> None:
        compose = (ROOT / "Laboutik/docker-compose.yml").read_text(encoding="utf-8")
        release = (ROOT / "tools/runtime/deploy-release.sh").read_text(encoding="utf-8")
        self.assertIn('"${LESPASS_PUBLIC_DOMAIN}:host-gateway"', compose)
        self.assertIn('"${FEDOW_PUBLIC_DOMAIN}:host-gateway"', compose)
        self.assertLess(release.index("configure_gala_apex"), release.index("docker exec -e DEBUG=1 laboutik_django"))

    def test_generated_keys_have_the_required_shapes(self) -> None:
        payload = generator.generated_payload()
        self.assertEqual(set(payload), renderer.GENERATED_FIELDS)
        self.assertEqual(len(payload["fedow_secret_key"]), 50)
        self.assertEqual(len(payload["laboutik_django_secret"]), 50)
        self.assertEqual(len(payload["lespass_django_secret"]), 50)
        for name in ("fedow_fernet_key", "laboutik_fernet_key", "lespass_fernet_key"):
            self.assertEqual(len(renderer.fernet_field(payload, name)), 44)
        self.assertEqual(len({payload["fedow_fernet_key"], payload["laboutik_fernet_key"], payload["lespass_fernet_key"]}), 3)

    def test_an_existing_current_version_is_never_replaced(self) -> None:
        with mock.patch.object(generator, "current_version_exists", return_value=True), mock.patch.object(generator, "aws") as aws:
            generator.initialize("example/generated", "gala-example")
        aws.assert_not_called()

    def test_shared_credentials_and_domains_are_assembled_without_overwriting_gala_keys(self) -> None:
        generated = generator.generated_payload()
        files = renderer.assemble(
            generated, STRIPE_TEST, SHARED_MAIL,
            "fedow.galas-am-aix.rezal.fr", "cashless.galas-am-aix.rezal.fr", "galas-am-aix.rezal.fr", True,
        )
        self.assertIn("DOMAIN='fedow.galas-am-aix.rezal.fr'", files["fedow.env"])
        self.assertIn("STRIPE_KEY_TEST='sk_test_example'", files["fedow.env"])
        self.assertIn("FEDOW_URL='https://fedow.galas-am-aix.rezal.fr/'", files["laboutik.env"])
        self.assertIn("MAIN_ASSET_NAME='Gala Example'", files["laboutik.env"])
        self.assertIn("EMAIL_HOST_PASSWORD='sample$#\\'password'", files["lespass.env"])
        self.assertIn("EMAIL_USE_TLS='1'", files["lespass.env"])
        self.assertIn("EMAIL_USE_SSL='0'", files["lespass.env"])
        self.assertIn("EMAIL_BACKEND='django.core.mail.backends.dummy.EmailBackend'", files["lespass.env"])
        self.assertIn("SUB='festival'", files["lespass.env"])
        self.assertIn("GALA_APEX_TENANT='1'", files["lespass.env"])
        self.assertIn("GALA_LOCAL_FEDOW='1'", files["lespass.env"])
        self.assertIn(f"ACTIVE_GALA_API_TOKEN='{generated['active_gala_api_token']}'", files["fedow.env"])
        self.assertIn(f"ACTIVE_GALA_API_TOKEN='{generated['active_gala_api_token']}'", files["lespass.env"])
        with tempfile.TemporaryDirectory() as directory:
            renderer.write_files(Path(directory), files)
            for filename in files:
                self.assertEqual(stat.S_IMODE(os.stat(Path(directory) / filename).st_mode), 0o600)

    def test_rejects_bad_shared_mode_and_generated_schema(self) -> None:
        generated = generator.generated_payload()
        domains = ("fedow.galas-am-aix.rezal.fr", "cashless.galas-am-aix.rezal.fr", "galas-am-aix.rezal.fr")
        with self.assertRaisesRegex(ValueError, "schema"):
            renderer.assemble({**generated, "unexpected": "value"}, STRIPE_TEST, SHARED_MAIL, *domains, True)
        with self.assertRaisesRegex(ValueError, "mode"):
            renderer.assemble(generated, {**STRIPE_TEST, "stripe": {**STRIPE_TEST["stripe"], "mode": "live"}}, SHARED_MAIL, *domains, True)
        with self.assertRaisesRegex(ValueError, "shared domains"):
            renderer.assemble(generated, STRIPE_TEST, SHARED_MAIL, "fedow.other.example.fr", *domains[1:], True)
        with self.assertRaisesRegex(ValueError, "mode"):
            renderer.assemble(generated, STRIPE_TEST, SHARED_MAIL, *domains, False)


if __name__ == "__main__":
    unittest.main()
