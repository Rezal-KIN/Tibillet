from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools/runtime/validate-release.py"
DIGEST = "0" * 64
VALID_RELEASE = {
    "release_id": "gala-am-aix-2027-v1.0.0",
    "gala_slug": "gala-am-aix-2027",
    "platform": "v1",
    "application_repository": "Rezal-KIN/Tibillet",
    "fork_commit": "0123456789abcdef0123456789abcdef01234567",
    "tibillet_upstream_commit": "0123456789abcdef0123456789abcdef01234567",
    "lespass_image": f"example/lespass@sha256:{DIGEST}",
    "fedow_image": f"example/fedow@sha256:{DIGEST}",
    "laboutik_image": f"example/laboutik@sha256:{DIGEST}",
    "traefik_image": f"example/traefik@sha256:{DIGEST}",
    "schema_generation": "v1",
}


def validate(document: dict[str, object]) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as manifest:
        json.dump(document, manifest)
        manifest.flush()
        return subprocess.run(
            [sys.executable, str(VALIDATOR), manifest.name],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )


class ReleaseManifestTests(unittest.TestCase):
    def test_accepts_fully_immutable_release(self) -> None:
        result = validate(VALID_RELEASE)

        self.assertEqual(result.returncode, 0)

    def test_rejects_wrong_application_repository(self) -> None:
        result = validate({**VALID_RELEASE, "application_repository": "Rezal-KIN/Gala-am-Aix-Tibillet"})

        self.assertEqual(result.returncode, 1)
        self.assertIn("application_repository", result.stderr)

    def test_rejects_mutable_component_image(self) -> None:
        result = validate({**VALID_RELEASE, "fedow_image": "tibillet/fedow:1.3.10"})

        self.assertEqual(result.returncode, 1)
        self.assertIn("fedow_image", result.stderr)

    def test_rejects_secret_or_deployment_scope(self) -> None:
        for field in ("secret_arn", "instance_id", "region", "backup", "dns", "preview", "action", "account_id"):
            with self.subTest(field=field):
                result = validate({**VALID_RELEASE, field: "forbidden"})

                self.assertEqual(result.returncode, 1)
                self.assertIn("must not contain", result.stderr)


if __name__ == "__main__":
    unittest.main()
