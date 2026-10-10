"""Exercise proxy startup/reuse in the actual release shell loop."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/runtime/deploy-release.sh"


class NginxDeploymentReloadTests(unittest.TestCase):
    def run_proxy(self, before, after, valid=True, reload_ok=True):
        source = SCRIPT.read_text()
        loop = source.split('for group in "${compose_groups[@]}"; do', 2)[2]
        loop = 'for group in "${compose_groups[@]}"; do' + loop.split(
            "\n# The upstream Lespass image", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "commands"
            started = Path(directory) / "started"
            harness = r'''
set -euo pipefail
compose_groups=(/repo/deploy/Lespass/docker-compose.yml)
compose_group_args() { COMPOSE_ARGS=(-f /test.compose); }
compose_env_file() { echo /test.env; }
fail() { echo "$*" >&2; exit 1; }
docker() {
  printf '%s\n' "$*" >> "$TEST_LOG"
  case "$1" in
    inspect)
      if [[ -e "$TEST_STARTED" ]]; then
        printf '%s\n' "$TEST_AFTER"
      elif [[ -n "$TEST_BEFORE" ]]; then
        printf '%s\n' "$TEST_BEFORE"
      else return 1; fi ;;
    compose) touch "$TEST_STARTED" ;;
    exec)
      if [[ "$*" == *'nginx -t' ]]; then
        [[ "$TEST_VALID" == 1 ]]
      else
        [[ -n "$TEST_BEFORE" && "$TEST_RELOAD_OK" == 1 ]]
      fi ;;
    *) return 1 ;;
  esac
}
'''
            env = dict(os.environ, TEST_LOG=str(log), TEST_STARTED=str(started),
                       TEST_BEFORE=before, TEST_AFTER=after,
                       TEST_VALID=str(int(valid)), TEST_RELOAD_OK=str(int(reload_ok)))
            result = subprocess.run(["bash", "-c", harness + loop], env=env,
                                    text=True, capture_output=True)
            return result.returncode, log.read_text()

    def test_first_boot_does_not_signal_new_proxy(self):
        status, commands = self.run_proxy("", "new-proxy")
        self.assertEqual(status, 0)
        self.assertIn("nginx -t", commands)
        self.assertNotIn("nginx -s reload", commands)

    def test_reused_proxy_reloads_changed_config(self):
        status, commands = self.run_proxy("same-proxy", "same-proxy")
        self.assertEqual(status, 0)
        self.assertIn("nginx -s reload", commands)

    def test_recreated_proxy_uses_its_startup_config(self):
        status, commands = self.run_proxy("old-proxy", "new-proxy")
        self.assertEqual(status, 0)
        self.assertNotIn("nginx -s reload", commands)

    def test_invalid_config_blocks_first_boot(self):
        status, _ = self.run_proxy("", "new-proxy", valid=False)
        self.assertNotEqual(status, 0)

    def test_reload_failure_still_blocks_reused_proxy(self):
        status, _ = self.run_proxy("same-proxy", "same-proxy", reload_ok=False)
        self.assertNotEqual(status, 0)
