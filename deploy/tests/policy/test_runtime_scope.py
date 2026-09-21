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
    "eu-north-1",
    "--instance",
    "i-0cd4e52913c8ae928",
    "--instance-name",
    "TibilletBapts",
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
    def test_allows_only_bapts(self) -> None:
        result = run()

        self.assertEqual(result.returncode, 0)
        self.assertIn("Runtime scope valid", result.stdout)

    def test_rejects_wrong_account(self) -> None:
        args = BASE.copy()
        args[args.index("318629836660")] = "051826693409"
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the Gala allowlist", result.stderr)

    def test_rejects_excluded_instance(self) -> None:
        args = BASE.copy()
        args[args.index("i-0cd4e52913c8ae928")] = "i-01107b29b967dc1dc"
        args[args.index("TibilletBapts")] = "Tibillet100J_OG"
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)

        self.assertEqual(result.returncode, 1)
        self.assertIn("instance i-01107b29b967dc1dc is outside", result.stderr)

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
