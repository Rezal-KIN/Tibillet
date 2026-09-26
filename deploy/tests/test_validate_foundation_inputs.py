from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools/validate-foundation-inputs.py"
COMMIT = "a" * 40
CONNECTION = "arn:aws:codeconnections:eu-west-3:318629836660:connection/01234567-89ab-cdef-0123-456789abcdef"


def environment(**overrides: str) -> dict[str, str]:
    values = {
        "AWS_DEFAULT_REGION": "eu-west-3",
        "GALA_NAME": "Gala Marseille",
        "SHARED_GALA_DOMAIN": "galas-am-aix.rezal.fr",
        "FOUNDATION_INSTANCE_TYPE": "t3.medium",
        "FOUNDATION_ROOT_VOLUME_SIZE_GIB": "40",
        "GITHUB_CONNECTION_ARN": CONNECTION,
        "FOUNDATION_SOURCE_COMMIT": COMMIT,
        "FOUNDATION_CODEBUILD_ROLE_ARN": "arn:aws:iam::318629836660:role/tibillet-gala-foundation-codebuild",
        "MANAGE_FOUNDATION_CODEBUILD_ROLE": "true",
        "TERRAFORM_STATE_BUCKET": "tibillet-gala-paris-318629836660-tfstate",
        "TERRAFORM_STATE_KEY": "infra/production.tfstate",
        "SSH_EMERGENCY_CIDRS": "disabled",
    }
    values.update(overrides)
    return {**os.environ, **values}


def run(catalog: dict[str, object], **overrides: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object], dict[str, object]]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        catalog_path = root / "catalog.json"
        output_path = root / "terraform.tfvars.json"
        proposal_path = root / "proposal.json"
        catalog_path.write_text(json.dumps({
            "vpc_id": "vpc-0123456789abcdef0",
            "subnet_id": "subnet-0123456789abcdef0",
            "ec2_ami_id": "ami-0123456789abcdef0",
            **catalog,
        }), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), str(output_path), "--catalog", str(catalog_path), "--catalog-output", str(proposal_path)],
            cwd=ROOT,
            env=environment(**overrides),
            text=True,
            capture_output=True,
            check=False,
        )
        output = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
        proposal = json.loads(proposal_path.read_text(encoding="utf-8")) if proposal_path.exists() else {}
        return result, output, proposal


class FoundationInputTests(unittest.TestCase):
    def test_temporary_gala_retirement_is_two_phase_and_preserves_aix(self) -> None:
        base = {
            "platform": "v1", "domain": "galas-am-aix.rezal.fr",
            "instance_type": "t3.medium", "root_volume_size_gib": 40,
            "ssh_emergency_cidrs": [], "associate_public_ip_address": True,
            "create_instance": True, "protect_from_destruction": True,
        }
        catalog = {"version": 1, "galas": {
            "gala-verification": dict(base), "gala-am-aix": dict(base),
        }}
        premature, _, _ = run(catalog, GALA_NAME="Retire Gala Verification")
        self.assertNotEqual(premature.returncode, 0)
        prepared, output, proposal = run(catalog, GALA_NAME="Prepare Gala Verification Retirement")
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertTrue(output["galas"]["gala-verification"]["create_instance"])
        self.assertFalse(output["galas"]["gala-verification"]["protect_from_destruction"])
        self.assertEqual(proposal["galas"]["gala-am-aix"], base)
        blocked, _, _ = run(proposal)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("finish Gala Verification Retirement", blocked.stderr)
        retired, output, proposal = run(proposal, GALA_NAME="Retire Gala Verification")
        self.assertEqual(retired.returncode, 0, retired.stderr)
        self.assertFalse(output["galas"]["gala-verification"]["create_instance"])
        self.assertEqual(proposal["galas"]["gala-am-aix"], base)

    def test_validation_retirement_requires_prepare_then_retires_only_instances(self) -> None:
        base = {
            "platform": "v1", "domain": "galas-am-aix.rezal.fr",
            "instance_type": "t3.medium", "root_volume_size_gib": 40,
            "ssh_emergency_cidrs": [], "associate_public_ip_address": True,
            "create_instance": True, "protect_from_destruction": True,
        }
        catalog = {"version": 1, "galas": {
            "gala-validation": dict(base), "gala-validation-2": dict(base),
            "gala-am-aix": dict(base),
        }}
        blocked, _, _ = run(catalog)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("Prepare Validation Retirement", blocked.stderr)
        premature, _, _ = run(catalog, GALA_NAME="Retire Validation Instances")
        self.assertNotEqual(premature.returncode, 0)
        prepared, output, proposal = run(catalog, GALA_NAME="Prepare Validation Retirement")
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        for slug in ("gala-validation", "gala-validation-2"):
            self.assertTrue(output["galas"][slug]["create_instance"])
            self.assertFalse(output["galas"][slug]["protect_from_destruction"])
        self.assertEqual(proposal["galas"]["gala-am-aix"], base)
        retired, output, proposal = run(proposal, GALA_NAME="Retire Validation Instances")
        self.assertEqual(retired.returncode, 0, retired.stderr)
        for slug in ("gala-validation", "gala-validation-2"):
            self.assertFalse(output["galas"][slug]["create_instance"])
        self.assertEqual(proposal["galas"]["gala-am-aix"], base)

    def test_smoke_pipeline_retirement_preserves_catalog(self) -> None:
        smoke = {
            "platform": "v1", "domain": "galas-am-aix.rezal.fr",
            "instance_type": "t3.medium", "root_volume_size_gib": 40,
            "ssh_emergency_cidrs": [], "associate_public_ip_address": True,
            "create_instance": True, "protect_from_destruction": True,
        }
        catalog = {"version": 1, "galas": {"gala-smoke": smoke}}
        result, output, proposal = run(catalog, GALA_NAME="Retire Smoke Production Pipeline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["galas"], catalog["galas"])
        self.assertEqual(proposal["galas"], catalog["galas"])
        result, _, _ = run({"version": 1, "galas": {}}, GALA_NAME="Retire Smoke Production Pipeline")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("existing Terraform-managed Smoke EC2", result.stderr)

    def test_adds_a_new_gala_to_an_empty_catalog(self) -> None:
        result, output, proposal = run({"version": 1, "galas": {}})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(output["galas"]), {"gala-marseille"})
        self.assertTrue(output["enable_production_pipeline"])
        self.assertTrue(output["enable_foundation_pipeline"])
        self.assertTrue(output["manage_foundation_codebuild_role"])
        self.assertEqual(proposal["vpc_id"], "vpc-0123456789abcdef0")
        self.assertEqual(output["galas"]["gala-marseille"]["ssh_emergency_cidrs"], [])
        self.assertTrue(output["galas"]["gala-marseille"]["associate_public_ip_address"])

    def test_preserves_existing_galas_in_the_proposed_state(self) -> None:
        catalog = {
            "version": 1,
            "vpc_id": "vpc-0123456789abcdef0",
            "subnet_id": "subnet-0123456789abcdef0",
            "ec2_ami_id": "ami-0123456789abcdef0",
            "galas": {
                "gala-am-aix": {
                    "platform": "v1",
                    "domain": "galas-am-aix.rezal.fr",
                    "instance_type": "t3.medium",
                    "root_volume_size_gib": 40,
                    "ssh_emergency_cidrs": [],
                    "create_instance": True,
                    "protect_from_destruction": True,
                }
            },
        }
        result, output, proposal = run(catalog)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(output["galas"]), {"gala-am-aix", "gala-marseille"})
        self.assertEqual(set(proposal["galas"]), {"gala-am-aix", "gala-marseille"})

    def test_existing_smoke_is_migrated_to_the_shared_domain(self) -> None:
        catalog = {
            "version": 1,
            "vpc_id": "vpc-0123456789abcdef0",
            "subnet_id": "subnet-0123456789abcdef0",
            "ec2_ami_id": "ami-0123456789abcdef0",
            "galas": {"gala-smoke": {"domain": "smoke.galas-am-aix.rezal.fr", "create_instance": True}},
        }
        result, output, proposal = run(catalog)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["galas"]["gala-smoke"]["domain"], "galas-am-aix.rezal.fr")
        self.assertEqual(proposal["galas"]["gala-smoke"]["domain"], "galas-am-aix.rezal.fr")

    def test_retry_of_existing_slug_is_idempotent(self) -> None:
        catalog = {
            "version": 1,
            "galas": {"gala-marseille": {
                "platform": "v1", "domain": "galas-am-aix.rezal.fr", "instance_type": "t3.medium",
                "root_volume_size_gib": 40, "ssh_emergency_cidrs": [],
                "associate_public_ip_address": True, "create_instance": True,
                "protect_from_destruction": True,
            }},
        }
        result, _, proposal = run(catalog)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(proposal["galas"], catalog["galas"])

    def test_rejects_a_different_public_domain(self) -> None:
        result, _, _ = run({"version": 1, "galas": {}}, SHARED_GALA_DOMAIN="other.example.fr")

        self.assertEqual(result.returncode, 1)
        self.assertIn("shared public domain", result.stderr)

    def test_uses_network_from_catalog(self) -> None:
        catalog = {
            "version": 1,
            "vpc_id": "vpc-0123456789abcdef0",
            "subnet_id": "subnet-0123456789abcdef0",
            "ec2_ami_id": "ami-0123456789abcdef0",
            "galas": {},
        }
        result, output, _ = run({**catalog, "vpc_id": "vpc-11111111111111111"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["vpc_id"], "vpc-11111111111111111")


if __name__ == "__main__":
    unittest.main()
