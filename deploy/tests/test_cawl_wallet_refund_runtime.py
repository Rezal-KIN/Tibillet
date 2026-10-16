"""The refund worker must run only against the intended CAWL container."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


RUNTIME = Path(__file__).resolve().parents[1] / 'tools/runtime'


class CawlWalletRefundWorkerTests(unittest.TestCase):
    def run_worker(self, provider='cawl', image='expected-image'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(RUNTIME / 'reconcile-cawl-wallet-refunds.sh', root / 'worker.sh')
            # Isolate the wrapper from a real host configuration, manifest and Docker.
            (root / 'lib.sh').write_text(
                'fail() { echo "$*" >&2; exit 1; }\n'
                'load_gala_config() { source "$1"; }\n'
                'require_command() { command -v "$1" >/dev/null; }\n'
                'deployed_manifest_path() { echo unused; }\n'
                'load_release_images() { FEDOW_IMAGE=expected-image; }\n')
            (root / 'gala.conf').write_text('PAYMENT_PROVIDER=' + provider + '\n')
            docker = root / 'docker'
            docker.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = inspect ]; then\n'
                '  case "$3" in *Running*) echo true ;; *Image*) echo "$MOCK_IMAGE" ;; esac\n'
                'else printf "%s\\n" "$*" >> "$MOCK_CALLS"; fi\n')
            docker.chmod(0o755)
            calls = root / 'calls'
            result = subprocess.run(['bash', str(root / 'worker.sh'), str(root / 'gala.conf')],
                env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'],
                     'MOCK_IMAGE': image, 'MOCK_CALLS': str(calls)}, capture_output=True, text=True)
            return result, calls.read_text() if calls.exists() else ''

    def test_cawl_runs_the_durable_queue_in_fedow(self):
        result, calls = self.run_worker()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.strip(), 'exec fedow_django poetry run python manage.py reconcile_cawl_wallet_refunds --limit 100')

    def test_stripe_never_invokes_the_cawl_worker(self):
        result, calls = self.run_worker(provider='stripe')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, '')

    def test_image_mismatch_stops_before_processing_money(self):
        result, calls = self.run_worker(image='previous-release')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, '')


if __name__ == '__main__':
    unittest.main()
