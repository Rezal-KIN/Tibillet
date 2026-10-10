"""A restrictive checkout umask must not make public styles unreadable."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


RELEASE = Path(__file__).resolve().parents[1] / "tools/runtime/deploy-release.sh"


class StaticMountPermissionsTests(unittest.TestCase):
    def test_private_checkout_is_repaired_without_changing_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            www = root / "deploy/Lespass/www"
            css = www / "static/reunion/css/tibillet.css"
            css.parent.mkdir(parents=True)
            css.write_text("body { color: white; }\n")
            for path in [www / "static", css.parent.parent, css.parent]:
                path.chmod(0o700)
            css.chmod(0o600)
            media = www / "media/private-upload.txt"
            media.parent.mkdir()
            media.write_text("private upload")
            media.chmod(0o600)
            protected = root / "protected"
            protected.mkdir(mode=0o700)
            private = protected / "private.txt"
            private.write_text("private configuration")
            private.chmod(0o600)
            (www / "static/outside").symlink_to(protected, target_is_directory=True)

            # Ownership discovery/preparation belongs to Docker/root on EC2.
            # Execute the real permission repair with those operations stubbed.
            bin_dir = root / "bin"
            bin_dir.mkdir()
            stubs = {
                "docker": "#!/bin/sh\nprintf '1000\\n'\n",
                "chown": "#!/bin/sh\nexit 0\n",
                "install": "#!/usr/bin/env python3\nimport os,sys\n"
                "args=[]; it=iter(sys.argv[1:])\n"
                "for value in it:\n"
                " if value in ('-o','-g'): next(it)\n"
                " else: args.append(value)\n"
                "os.execv('/usr/bin/install',['install',*args])\n",
            }
            for name, content in stubs.items():
                tool = bin_dir / name
                tool.write_text(content)
                tool.chmod(0o755)
            source = RELEASE.read_text()
            function = "prepare_writable_mounts() {" + source.split(
                "prepare_writable_mounts() {", 1
            )[1].split("\n}\n", 1)[0] + "\n}\n"
            result = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + function
                 + '\nprepare_writable_mounts image tibillet "$1"', "repair", str(www)],
                env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "REPO_ROOT": str(root)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for path in [www / "static", css.parent.parent, css.parent]:
                self.assertEqual(path.stat().st_mode & 0o777, 0o755)
            self.assertEqual(css.stat().st_mode & 0o777, 0o644)
            self.assertEqual(css.read_text(), "body { color: white; }\n")
            self.assertEqual(media.stat().st_mode & 0o777, 0o600)
            self.assertEqual(protected.stat().st_mode & 0o777, 0o700)
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
