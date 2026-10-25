from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools/runtime/reclaim-deployment-space.sh"


class DeploymentSpaceTests(unittest.TestCase):
    def run_check(self, before: int, after: int, threshold: str = "10485760") -> tuple[subprocess.CompletedProcess[str], bool]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            marker = root / "pruned"
            df = bin_dir / "df"
            df.write_text(
                "#!/bin/sh\n"
                "echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
                "if [ -e \"$MOCK_PRUNE_MARKER\" ]; then available=$MOCK_AFTER_KIB; "
                "else available=$MOCK_BEFORE_KIB; fi\n"
                "echo \"/dev/root 40000000 30000000 $available 75% /\"\n",
                encoding="utf-8",
            )
            docker = bin_dir / "docker"
            docker.write_text(
                "#!/bin/sh\n"
                "[ \"$1 $2 $3 $4\" = 'image prune --all --force' ] || exit 2\n"
                "touch \"$MOCK_PRUNE_MARKER\"\n",
                encoding="utf-8",
            )
            df.chmod(0o755)
            docker.chmod(0o755)
            config = root / "gala.conf"
            config.write_text(
                f'GALA_SLUG="gala-smoke"\nAWS_REGION="eu-west-3"\n'
                f'BACKUP_BUCKET="test-backups"\nREPO_ROOT="{root}"\n'
                f'MIN_FREE_SPACE_KIB="{threshold}"\n',
                encoding="utf-8",
            )
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
                   "MOCK_PRUNE_MARKER": str(marker),
                   "MOCK_BEFORE_KIB": str(before), "MOCK_AFTER_KIB": str(after)}
            result = subprocess.run(["bash", str(SCRIPT), str(config)],
                                    text=True, capture_output=True, env=env, check=False)
            return result, marker.exists()

    def test_no_prune_when_reserve_already_met(self) -> None:
        result, pruned = self.run_check(11_000_000, 11_000_000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(pruned)

    def test_prunes_only_unused_images_when_reserve_is_low(self) -> None:
        result, pruned = self.run_check(9_649_900, 15_000_000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(pruned)
        self.assertIn("reclaiming unused Docker images", result.stdout)

    def test_refuses_deployment_if_cleanup_is_insufficient(self) -> None:
        result, pruned = self.run_check(9_649_900, 9_800_000)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(pruned)
        self.assertIn("less than required free space", result.stderr)

    def test_rejects_invalid_threshold_without_pruning(self) -> None:
        result, pruned = self.run_check(9_649_900, 15_000_000, "not-a-number")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(pruned)


if __name__ == "__main__":
    unittest.main()
