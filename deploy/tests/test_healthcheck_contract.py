from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


HEALTHCHECK = Path(__file__).resolve().parents[1] / "tools/runtime/healthcheck.sh"


class HealthcheckContractTests(unittest.TestCase):
    def test_http_success_does_not_hide_a_failed_celery_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            curl = bin_dir / "curl"
            curl.write_text("#!/bin/sh\nprintf 200\n", encoding="utf-8")
            docker = bin_dir / "docker"
            docker.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  inspect) printf '%s\\n' \"$MOCK_CELERY_RUNNING\" ; exit 0 ;;\n"
                "  exec) [ \"$MOCK_CELERY_PING\" = true ] ; exit $? ;;\n"
                "esac\nexit 2\n",
                encoding="utf-8",
            )
            curl.chmod(0o755)
            docker.chmod(0o755)
            timeout = bin_dir / "timeout"
            timeout.write_text("#!/bin/sh\nshift\nexec \"$@\"\n", encoding="utf-8")
            timeout.chmod(0o755)
            config = root / "gala.conf"
            config.write_text(
                f'GALA_SLUG="gala-smoke"\nAWS_REGION="eu-west-3"\n'
                f'BACKUP_BUCKET="test-bucket"\nREPO_ROOT="{root}"\n'
                'FEDOW_PUBLIC_DOMAIN="fedow.galas-am-aix.rezal.fr"\n'
                'LABOUTIK_PUBLIC_DOMAIN="cashless.galas-am-aix.rezal.fr"\n'
                'LESPASS_PUBLIC_DOMAIN="galas-am-aix.rezal.fr"\n'
                'HEALTHCHECK_URLS="https://fedow.galas-am-aix.rezal.fr/,https://cashless.galas-am-aix.rezal.fr/,https://galas-am-aix.rezal.fr/"\n',
                encoding="utf-8",
            )
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            for running, ping, expected_success in (
                ("false", "false", False),
                ("true", "false", False),
                ("true", "true", True),
            ):
                with self.subTest(running=running, ping=ping):
                    result = subprocess.run(
                        ["bash", str(HEALTHCHECK), str(config)],
                        env={**env, "MOCK_CELERY_RUNNING": running, "MOCK_CELERY_PING": ping},
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode == 0, expected_success, result.stderr)


if __name__ == "__main__":
    unittest.main()
