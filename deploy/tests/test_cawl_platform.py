"""Contrat de la chaîne CAWL parallèle. / Parallel CAWL delivery contract."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_validate_foundation_inputs import run


ROOT = Path(__file__).resolve().parents[1]
CAWL = "gala-smoke-cawl"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plan = load("verify_foundation_plan_cawl", ROOT / "tools/verify-foundation-plan.py")
smoke = load("create_smoke_manifest_cawl", ROOT / "tools/create-smoke-manifest.py")
promotion = load("validate_promotion_cawl", ROOT / "tools/validate-promotion.py")
preparer = load("reconcile_runtime_cawl", ROOT / "tools/runtime/reconcile-runtime.py")
deployer = load("deploy_smoke_candidate_cawl", ROOT / "tools/deploy-smoke-candidate.py")

PREFIX = "arn:aws:secretsmanager:eu-west-3:318629836660:secret:tibillet-gala-paris/"
EXISTING = {
    "gala-smoke": {"platform": "v1", "domain": "galas-am-aix.rezal.fr", "instance_type": "t3.medium",
                   "root_volume_size_gib": 40, "ssh_emergency_cidrs": [], "associate_public_ip_address": True,
                   "create_instance": True, "protect_from_destruction": True},
}


def change(address: str, actions: list[str]) -> dict[str, object]:
    return {"address": address, "change": {"actions": actions}}


def candidate(commit: str) -> dict[str, object]:
    return {'application_repository': 'Rezal-KIN/Tibillet', 'fork_commit': commit, 'platform': 'v1',
            'lespass_image': 'ecr/cawl/lespass@sha256:' + 'a' * 64,
            'fedow_image': 'ecr/cawl/fedow@sha256:' + 'b' * 64,
            'laboutik_image': 'ecr/cawl/laboutik@sha256:' + 'c' * 64,
            'image_builds': {component: {'base_image': 'native/' + component + '@sha256:' + 'd' * 64,
                                         'source_commit': commit} for component in ('fedow', 'laboutik')}}


PINNED = {'schema_version': 1, 'traefik_image': 'traefik@sha256:' + 'e' * 64}


class FoundationCatalogueTests(unittest.TestCase):
    def test_enable_operation_adds_only_the_cawl_smoke_and_enables_the_chain(self) -> None:
        result, output, proposal = run({"version": 1, "galas": json.loads(json.dumps(EXISTING))},
                                       GALA_NAME="Enable CAWL Platform")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output["enable_cawl_platform"])
        self.assertEqual(proposal["galas"][CAWL]["payment_provider"], "cawl")
        # FR : L'entrée Stripe existante reste octet pour octet identique.
        self.assertEqual(proposal["galas"]["gala-smoke"], EXISTING["gala-smoke"])

    def test_stripe_gala_keeps_historical_shape_and_chain_stays_disabled(self) -> None:
        result, output, proposal = run({"version": 1, "galas": json.loads(json.dumps(EXISTING))})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(output["enable_cawl_platform"])
        self.assertNotIn("payment_provider", proposal["galas"]["gala-marseille"])

    def test_cawl_gala_requires_the_cawl_smoke_first(self) -> None:
        result, _, _ = run({"version": 1, "galas": json.loads(json.dumps(EXISTING))}, PAYMENT_PROVIDER="cawl")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Enable CAWL Platform", result.stderr)

    def test_cawl_foundation_records_the_provider_and_keeps_the_chain(self) -> None:
        galas = json.loads(json.dumps(EXISTING))
        galas[CAWL] = {**EXISTING["gala-smoke"], "payment_provider": "cawl"}
        result, output, proposal = run({"version": 1, "galas": galas}, GALA_NAME="Gala Lyon", PAYMENT_PROVIDER="cawl")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output["enable_cawl_platform"])
        self.assertEqual(proposal["galas"]["gala-lyon"]["payment_provider"], "cawl")

    def test_cawl_smoke_slug_and_unknown_provider_are_refused(self) -> None:
        for overrides in ({"GALA_NAME": "Gala Smoke CAWL"}, {"PAYMENT_PROVIDER": "paypal"},
                          {"GALA_NAME": "Enable CAWL Platform", "PAYMENT_PROVIDER": "cawl"}):
            result, _, _ = run({"version": 1, "galas": json.loads(json.dumps(EXISTING))}, **overrides)
            self.assertNotEqual(result.returncode, 0, overrides)


class FoundationPlanTests(unittest.TestCase):
    def test_enable_operation_accepts_exactly_the_cawl_chain(self) -> None:
        changes = [change(address, ["create"]) for address in sorted(plan.CAWL_PLATFORM_ADDRESSES)]
        changes += [change(f'module.gala["{CAWL}"].aws_instance.runtime[0]', ["create"]),
                    change(f'aws_ssm_document.production_deploy["{CAWL}"]', ["create"])]
        accepted = plan.verify({"resource_changes": changes}, CAWL, extra_new=plan.CAWL_PLATFORM_ADDRESSES)
        self.assertEqual(len(accepted), len(changes))

    def test_normal_gala_creation_cannot_create_the_cawl_chain(self) -> None:
        with self.assertRaises(ValueError):
            plan.verify({"resource_changes": [change('aws_codepipeline.test_cawl[0]', ["create"])]}, "gala-lyon")

    def test_enable_operation_cannot_touch_the_stripe_chain(self) -> None:
        for address, actions in (('aws_codepipeline.test[0]', ["update"]),
                                 ('aws_secretsmanager_secret.stripe_live[0]', ["delete"]),
                                 ('module.gala["gala-am-aix"].aws_instance.runtime[0]', ["update"])):
            with self.assertRaises(ValueError, msg=address):
                plan.verify({"resource_changes": [change(address, actions)]}, CAWL,
                            extra_new=plan.CAWL_PLATFORM_ADDRESSES)


class SmokeAndPromotionTests(unittest.TestCase):
    def test_cawl_smoke_manifest_targets_only_the_cawl_smoke(self) -> None:
        manifest = smoke.create(candidate('c' * 40), PINNED, gala_slug=CAWL)
        self.assertEqual(manifest["gala_slug"], CAWL)
        with self.assertRaises(ValueError):
            smoke.create(candidate('c' * 40), PINNED, gala_slug="gala-am-aix")

    def test_cawl_smoke_deployment_writes_its_own_release_and_proof_prefixes(self) -> None:
        commit = 'c' * 40
        manifest = smoke.create(candidate(commit), PINNED, gala_slug=CAWL)
        written: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            environment = {"SMOKE_GALA_SLUG": CAWL, "SMOKE_INSTANCE_ID": "i-0123456789abcdef0",
                           "RELEASE_BUCKET": "bucket", "SMOKE_DEPLOY_DOCUMENT": "doc"}
            with patch.dict(os.environ, environment), patch.object(sys, "argv", ["deploy", str(path)]), \
                    patch.object(deployer.subprocess, "check_output", return_value=commit + "\n"), \
                    patch.object(deployer, "aws", return_value={"Account": "318629836660"}), \
                    patch.object(deployer, "send"), \
                    patch.object(deployer, "put_immutable", side_effect=lambda bucket, key, body: written.append(key)):
                deployer.main()
        self.assertEqual(written, [f"releases/{CAWL}/{manifest['release_id']}.json",
                                   f"test-validated-cawl/{manifest['release_id']}.json"])

    def test_stripe_smoke_cannot_deploy_a_cawl_manifest(self) -> None:
        manifest = smoke.create(candidate('c' * 40), PINNED, gala_slug=CAWL)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.dict(os.environ, {"SMOKE_GALA_SLUG": "gala-smoke"}), \
                    patch.object(sys, "argv", ["deploy", str(path)]):
                with self.assertRaises(ValueError):
                    deployer.main()

    def test_production_refuses_both_smoke_hosts(self) -> None:
        tested = smoke.create(candidate('c' * 40), PINNED, gala_slug=CAWL)
        for slug in ("gala-smoke", CAWL):
            with self.assertRaises(ValueError):
                promotion.compare({**tested, "gala_slug": slug}, tested, slug)


class RuntimeSecretTests(unittest.TestCase):
    def test_cawl_smoke_requires_the_shared_test_secret_and_explicit_provider(self) -> None:
        generated = PREFIX + f"galas/{CAWL}/generated-AbC123"
        mail = PREFIX + "shared/integrations-mail-AbC123"
        original = f'GALA_SLUG="{CAWL}"\nDEPLOYMENT_LOCKED=true\n'
        shared = PREFIX + "shared/integrations-stripe-test-AbC123"
        result = preparer.update(original, CAWL, generated, shared, mail, "cawl")
        self.assertIn('PAYMENT_PROVIDER="cawl"', result)
        for wrong in ("integrations-stripe-live", "integrations-cawl-test"):
            with self.assertRaises(ValueError):
                preparer.update(original, CAWL, generated, PREFIX + f"shared/{wrong}-AbC123", mail, "cawl")
        with self.assertRaises(ValueError):
            preparer.update(original, CAWL, generated, shared, mail)


class TerraformWiringTests(unittest.TestCase):
    def test_cawl_chain_uses_its_own_branch_marker_and_smoke(self) -> None:
        terraform = (ROOT / "infra/terraform/cawl-delivery.tf").read_text(encoding="utf-8")
        self.assertIn('BranchName           = var.cawl_source_branch', terraform)
        self.assertIn('"${aws_s3_bucket.backups[0].arn}/${local.smoke_marker_prefix.cawl}/smoke-*.json"', terraform)
        self.assertIn('module.gala[local.cawl_smoke_slug].instance_id', terraform)
        self.assertNotIn('test-validated/', terraform)
        locals_tf = (ROOT / "infra/terraform/locals.tf").read_text(encoding="utf-8")
        self.assertIn('smoke_marker_prefix = { stripe = "test-validated", cawl = "test-validated-cawl" }', locals_tf)


if __name__ == "__main__":
    unittest.main()
