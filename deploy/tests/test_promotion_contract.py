from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = load("create_smoke_manifest", ROOT / "tools/create-smoke-manifest.py")
promotion = load("validate_promotion", ROOT / "tools/validate-promotion.py")
preparer = load("reconcile_runtime", ROOT / "tools/runtime/reconcile-runtime.py")


class PromotionContractTests(unittest.TestCase):
    def test_smoke_manifest_uses_the_exact_commit_and_pinned_stack(self) -> None:
        commit = "a" * 40
        candidate = {
            "application_repository": "Rezal-KIN/Tibillet", "fork_commit": commit,
            "platform": "v1", "lespass_image": "ecr/lespass@sha256:" + "a" * 64,
        }
        pinned = {"schema_version": 1, **{
            key: "image@sha256:" + char * 64
            for key, char in (("fedow_image", "b"), ("laboutik_image", "c"), ("traefik_image", "d"))
        }}
        manifest = smoke.create(candidate, pinned)
        self.assertEqual(manifest["release_id"], f"smoke-{commit}")
        production = {**manifest, "gala_slug": "gala-validation", "release_id": "validation-v1"}
        promotion.compare(production, manifest, "gala-validation")
        with self.assertRaisesRegex(ValueError, "differs"):
            promotion.compare({**production, "fedow_image": "image@sha256:" + "e" * 64}, manifest, "gala-validation")

    def test_smoke_runtime_reconciliation_is_idempotent(self) -> None:
        stripe = "arn:aws:secretsmanager:eu-west-3:318629836660:secret:tibillet-gala-paris/shared/integrations-stripe-test-AbC123"
        mail = "arn:aws:secretsmanager:eu-west-3:318629836660:secret:tibillet-gala-paris/shared/integrations-mail-AbC123"
        generated = "arn:aws:secretsmanager:eu-west-3:318629836660:secret:tibillet-gala-paris/galas/gala-smoke/generated-AbC123"
        original = 'GALA_SLUG="gala-smoke"\nDEPLOYMENT_LOCKED=true\n'
        once = preparer.update(original, "gala-smoke", generated, stripe, mail)
        self.assertEqual(preparer.update(once, "gala-smoke", generated, stripe, mail), once)
        self.assertIn('DEPLOYMENT_LOCKED="false"', once)
        with self.assertRaisesRegex(ValueError, "Stripe test"):
            preparer.update(original, "gala-smoke", generated, mail, mail)


if __name__ == "__main__":
    unittest.main()
