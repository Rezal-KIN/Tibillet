"""An explicit no-backup decision cannot authorize another release or persist."""
import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/runtime/release-backup-exception.py'
spec = importlib.util.spec_from_file_location('backup_exception', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReleaseBackupExceptionTests(unittest.TestCase):
    def test_exact_release_expiry_permissions_and_gala_binding(self):
        manifest = {'gala_slug': 'gala-smoke-cawl', 'release_id': 'qa',
                    'fork_commit': 'a' * 40, 'lespass_image': 'image@sha256:' + 'b' * 64}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertFalse(module.permitted(root, 'gala-smoke-cawl', manifest, now=1000))
            path = module.grant(root, 'gala-smoke-cawl', module.manifest_digest(manifest),
                                2000, 'User requested this release without a new backup', now=1000)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(module.permitted(root, 'gala-smoke-cawl', manifest, now=1001))
            self.assertFalse(module.permitted(root, 'bapts2026', manifest, now=1001))
            self.assertFalse(module.permitted(root, 'gala-smoke-cawl', manifest, now=2000))
            for key in ['release_id', 'fork_commit', 'lespass_image']:
                changed = {**manifest, key: 'different'}
                self.assertFalse(module.permitted(root, 'gala-smoke-cawl', changed, now=1001))
            changed = copy.deepcopy(manifest);changed['card_stock'] = {'lots': ['different']}
            self.assertFalse(module.permitted(root, 'gala-smoke-cawl', changed, now=1001))
            path.chmod(0o644)
            self.assertFalse(module.permitted(root, 'gala-smoke-cawl', manifest, now=1001))
            path.chmod(0o600)
            contents = path.read_bytes();path.unlink()
            target = root / 'untrusted.json';target.write_bytes(contents);target.chmod(0o600)
            path.symlink_to(target)
            self.assertFalse(module.permitted(root, 'gala-smoke-cawl', manifest, now=1001))

    def test_no_broad_indefinite_or_silent_repeated_authorization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for expiry in [999, 1000, 87401]:
                with self.assertRaises(ValueError):
                    module.grant(root, 'bapts2026', 'a' * 64, expiry, 'Approved', now=1000)
            with self.assertRaises(ValueError):
                module.grant(root, '../other', 'a' * 64, 2000, 'Approved', now=1000)
            module.grant(root, 'bapts2026', 'a' * 64, 2000, 'Approved', now=1000)
            with self.assertRaises(FileExistsError):
                module.grant(root, 'bapts2026', 'a' * 64, 2000, 'Approved', now=1000)


if __name__ == '__main__':
    unittest.main()
