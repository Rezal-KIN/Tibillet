from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "tools/validate-runtime-scope.py"
BASE = [
    sys.executable,
    str(VALIDATOR),
    "--account",
    "318629836660",
    "--region",
    "eu-west-3",
    "--instance",
    "i-00000000000000000",
    "--instance-name",
    "tibillet-gala-not-provisioned",
]


def run(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*BASE, *extra],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class RuntimeScopeTests(unittest.TestCase):
    def test_allows_provisioning_placeholder_only(self) -> None:
        result = run()

        self.assertEqual(result.returncode, 0)
        self.assertIn("Runtime scope valid", result.stdout)

    def test_rejects_wrong_account(self) -> None:
        args = BASE.copy()
        args[args.index("318629836660")] = "051826693409"
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the Gala allowlist", result.stderr)

    def test_rejects_stockholm_region(self) -> None:
        args = BASE.copy()
        args[args.index("eu-west-3")] = "eu-north-1"
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the Gala runtime allowlist", result.stderr)

    def test_rejects_unapproved_instance(self) -> None:
        args = BASE.copy()
        args[args.index("i-00000000000000000")] = "i-0123456789abcdef0"
        args[args.index("tibillet-gala-not-provisioned")] = "tibillet-gala-gala-am-aix-2027"
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)

        self.assertEqual(result.returncode, 1)
        self.assertIn("instance i-0123456789abcdef0 is outside", result.stderr)

    def test_rejects_legacy_references(self) -> None:
        for reference in (
            "Tibillet100J_OG",
            "Laboutik_100-jours-225",
            "PPSCP",
            "TibilletSiteKfet",
            "Lespass-v2",
            "tools/start-stacks-on-boot.sh",
            "tools/scripts/backup_soldes.sh",
            "tools/scripts/reset_soldes.sh",
        ):
            with self.subTest(reference=reference):
                result = run("--reference", reference)

                self.assertEqual(result.returncode, 1)
                self.assertIn("explicitly denied", result.stderr)


if __name__ == "__main__":
    unittest.main()
