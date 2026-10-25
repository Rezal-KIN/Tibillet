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
            curl.write_text(
                '#!/bin/sh\ncase "$*" in\n'
                '  */static/*) printf "%s" "$MOCK_STATIC_STATUS" ;;\n'
                '  *) printf 200 ;;\nesac\n', encoding="utf-8",
            )
            docker = bin_dir / "docker"
            docker.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  inspect) printf '%s\\n' \"$MOCK_CELERY_RUNNING\" ; exit 0 ;;\n"
                "  exec) if [ \"$2\" = lespass_celery ] && [ \"$3\" = curl ]; then\n"
                "          [ \"$MOCK_WORKER_FEDOW\" = true ]; exit $?; fi\n"
                "        [ \"$MOCK_CELERY_PING\" = true ] ; exit $? ;;\n"
                "esac\nexit 2\n",
                encoding="utf-8",
            )
            curl.chmod(0o755)
            docker.chmod(0o755)
            timeout = bin_dir / "timeout"
            timeout.write_text("#!/bin/sh\nshift\nexec \"$@\"\n", encoding="utf-8")
            timeout.chmod(0o755)
            python = bin_dir / "python3"
            python.write_text(
                '#!/bin/sh\ncase "$1" in\n'
                '  */configure-gala-admin.py) [ "$MOCK_ADMIN_READY" = true ]; exit $? ;;\n'
                '  */configure-gala-refill-domain.py) [ "$MOCK_REFILL_DOMAIN_READY" = true ]; exit $? ;;\n'
                'esac\nexit 2\n', encoding="utf-8",
            )
            python.chmod(0o755)
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
            for running, ping, admin, domain, worker_fedow, static_status, expected_success in (
                ("false", "false", "true", "true", "true", "200", False),
                ("true", "false", "true", "true", "true", "200", False),
                ("true", "true", "false", "true", "true", "200", False),
                ("true", "true", "true", "false", "true", "200", False),
                ("true", "true", "true", "true", "false", "200", False),
                ("true", "true", "true", "true", "true", "403", False),
                ("true", "true", "true", "true", "true", "404", False),
                ("true", "true", "true", "true", "true", "200", True),
            ):
                with self.subTest(running=running, ping=ping, admin=admin, domain=domain, static_status=static_status):
                    result = subprocess.run(
                        ["bash", str(HEALTHCHECK), str(config)],
                        env={**env, "MOCK_CELERY_RUNNING": running, "MOCK_CELERY_PING": ping,
                             "MOCK_ADMIN_READY": admin, "MOCK_REFILL_DOMAIN_READY": domain,
                             "MOCK_WORKER_FEDOW": worker_fedow, "MOCK_STATIC_STATUS": static_status},
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode == 0, expected_success, result.stderr)
                    if static_status != "200":
                        self.assertIn("Lespass stylesheet unavailable", result.stderr)


if __name__ == "__main__":
    unittest.main()
