"""Fresh and existing Gala hosts receive the same memory safety net."""

import unittest
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[1] / "tools" / "runtime"


class HostSwapContractTests(unittest.TestCase):
    def test_runtime_install_provisions_swap_before_applications(self):
        install = (RUNTIME / "install-runtime-contract.sh").read_text(encoding="utf-8")
        self.assertIn('bash "$REPO_ROOT/deploy/tools/runtime/ensure-host-swap.sh"', install)
        self.assertLess(install.index("ensure-host-swap.sh"), install.index("for script in"))
        self.assertIn("  ensure-host-swap.sh fetch-runtime-secret.sh", install)

    def test_swap_is_persistent_and_does_not_replace_an_existing_file(self):
        script = (RUNTIME / "ensure-host-swap.sh").read_text(encoding="utf-8")
        self.assertIn("swap_bytes=2147483648", script)
        self.assertIn('[[ -f "$swap_file" && ! -L "$swap_file" ]]', script)
        self.assertIn('swapon "$swap_file"', script)
        self.assertIn('>> /etc/fstab', script)
        self.assertIn('vm.swappiness = 10', script)


if __name__ == "__main__":
    unittest.main()
