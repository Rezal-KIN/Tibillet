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
        "GALA_SLUG": "gala-marseille",
        "GALA_DOMAIN": "galas-marseille.rezal.fr",
        "INSTANCE_TYPE": "t3.medium",
        "ROOT_VOLUME_SIZE_GIB": "40",
        "VPC_ID": "vpc-0123456789abcdef0",
        "SUBNET_ID": "subnet-0123456789abcdef0",
        "EC2_AMI_ID": "ami-0123456789abcdef0",
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
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
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
    def test_adds_a_new_gala_to_an_empty_catalog(self) -> None:
        result, output, proposal = run({"version": 1, "galas": {}})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(output["galas"]), {"gala-marseille"})
        self.assertTrue(output["enable_production_pipeline"])
        self.assertTrue(output["enable_foundation_pipeline"])
        self.assertTrue(output["manage_foundation_codebuild_role"])
        self.assertEqual(proposal["vpc_id"], "vpc-0123456789abcdef0")
        self.assertEqual(output["galas"]["gala-marseille"]["ssh_emergency_cidrs"], [])

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

    def test_rejects_a_duplicate_slug(self) -> None:
        catalog = {
            "version": 1,
            "galas": {"gala-marseille": {"platform": "v1"}},
        }
        result, _, _ = run(catalog)

        self.assertEqual(result.returncode, 1)
        self.assertIn("already exists", result.stderr)

    def test_rejects_a_network_different_from_the_catalog(self) -> None:
        catalog = {
            "version": 1,
            "vpc_id": "vpc-0123456789abcdef0",
            "subnet_id": "subnet-0123456789abcdef0",
            "ec2_ami_id": "ami-0123456789abcdef0",
            "galas": {},
        }
        result, _, _ = run(catalog, VPC_ID="vpc-11111111111111111")

        self.assertEqual(result.returncode, 1)
        self.assertIn("must match", result.stderr)


if __name__ == "__main__":
    unittest.main()
