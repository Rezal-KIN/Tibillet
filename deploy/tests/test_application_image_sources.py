"""A deployment cannot substitute an image built from other code."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / 'tools/runtime'
sys.path.insert(0, str(RUNTIME))
spec = importlib.util.spec_from_file_location('check_application_images', RUNTIME / 'validate-application-images.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class ApplicationImageTests(unittest.TestCase):
    def test_labels_must_match_the_recorded_sources_before_startup(self):
        commit = 'a' * 40
        builds = {component: {'base_image': 'native/' + component + '@sha256:' + 'b' * 64,
                              'source_commit': commit} for component in ('fedow', 'laboutik')}
        manifest = {'fork_commit': commit, 'image_builds': builds,
                    **{component + '_image': 'ecr/' + component + '@sha256:' + 'c' * 64 for component in builds}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.json'
            path.write_text(json.dumps(manifest))
            def inspect(command, **kwargs):
                component = 'fedow' if '/fedow@' in command[-1] else 'laboutik'
                return json.dumps({'org.opencontainers.image.revision': commit,
                                   'org.opencontainers.image.base.name': builds[component]['base_image']})
            with patch.object(sys, 'argv', ['check', str(path)]), patch.object(check.subprocess, 'check_output', side_effect=inspect), patch('sys.stdout', new=io.StringIO()):
                check.main()
            with patch.object(sys, 'argv', ['check', str(path)]), patch.object(check.subprocess, 'check_output', return_value='{}'):
                with self.assertRaisesRegex(ValueError, 'labels'):
                    check.main()

    def test_new_runtime_does_not_silently_use_unmodified_reference_images(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.json'
            path.write_text('{}')
            with patch.object(sys, 'argv', ['check', str(path)]):
                with self.assertRaisesRegex(ValueError, 'new Test build'):
                    check.main()


if __name__ == '__main__':
    unittest.main()
