"""S3 uploads freeze before any import and bind the Test promotion proof."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/runtime'))
from card_stock import smoke_release_id


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


uploads = load('uploaded_stock', 'freeze-uploaded-card-stock.py')
promotion = load('uploaded_promotion', 'validate-promotion.py')
CSV = b'https://galas-am-aix.rezal.fr/qr/11111111-1111-4111-8111-111111111111,11111111,AABBCCDD\n'


class UploadedStockTests(unittest.TestCase):
    def obj(self, generation=1, name='lot.csv'):
        return {'Key': f'{uploads.PREFIX}{generation}/{name}', 'Size': len(CSV), 'ETag': '"snapshot"'}

    def test_generation_directories_and_invalid_inputs(self):
        obj = self.obj()
        self.assertEqual(uploads.select([obj, {'Key': uploads.PREFIX, 'Size': 0}]),
                         [(1, obj['Key'], '"snapshot"')])
        for values in ([], [self.obj(0)], [self.obj(2147483648)], [self.obj(name='nested/lot.csv')],
                       [self.obj(name='lot.xlsx')], [{**obj, 'Size': 0}],
                       [{**obj, 'Size': uploads.MAX_CSV_BYTES + 1}]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                uploads.select(values)

    def test_frozen_bytes_published_once_and_temp_files_removed(self):
        downloads, publications = [], []
        def aws(command, **kwargs):
            if 'list-objects-v2' in command:
                return subprocess.CompletedProcess(command, 0, json.dumps({'Contents': [self.obj()]}))
            if 'get-object' in command:
                self.assertEqual(command[command.index('--if-match') + 1], '"snapshot"')
                path = Path(command[-1]); path.write_bytes(CSV); downloads.append(path)
            if 'put-object' in command:
                self.assertIn('--if-none-match', command)
                publications.append(Path(command[command.index('--body')+1]).read_bytes())
            return subprocess.CompletedProcess(command, 0, '{}')
        with tempfile.TemporaryDirectory() as directory, patch.object(subprocess, 'run', side_effect=aws):
            output = Path(directory) / 'stock.json'
            catalogue = uploads.freeze(['aws'], 'private', 'galas-am-aix.rezal.fr', output)
            self.assertEqual(json.loads(output.read_text()), catalogue)
            self.assertEqual(publications, [CSV])
            self.assertEqual(catalogue['lots'][0]['rows'], 1)
        self.assertTrue(all(not path.exists() for path in downloads))

    def test_duplicates_rejected_before_any_publication(self):
        def aws(command, **kwargs):
            self.assertNotIn('put-object', command)
            if 'list-objects-v2' in command:
                return subprocess.CompletedProcess(command, 0, json.dumps({'Contents': [self.obj(1), self.obj(2)]}))
            Path(command[-1]).write_bytes(CSV)
            return subprocess.CompletedProcess(command, 0, '{}')
        with tempfile.TemporaryDirectory() as directory, patch.object(subprocess, 'run', side_effect=aws):
            output = Path(directory) / 'stock.json'
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                uploads.freeze(['aws'], 'private', 'galas-am-aix.rezal.fr', output)
            self.assertFalse(output.exists())

    def test_concurrent_replacement_aborts_before_publish(self):
        def aws(command, **kwargs):
            if 'list-objects-v2' in command:
                return subprocess.CompletedProcess(command, 0, json.dumps({'Contents': [self.obj()]}))
            self.assertIn('get-object', command)
            raise subprocess.CalledProcessError(1, command, stderr='PreconditionFailed')
        with tempfile.TemporaryDirectory() as directory, patch.object(subprocess, 'run', side_effect=aws):
            output = Path(directory) / 'stock.json'
            with self.assertRaises(subprocess.CalledProcessError):
                uploads.freeze(['aws'], 'private', 'galas-am-aix.rezal.fr', output)
            self.assertFalse(output.exists())

    def test_same_code_new_generation_has_separate_test_proof(self):
        lot = {'generation': 1, 'rows': 1, 'sha256': 'a'*64, 'key': 'card-stock/'+'a'*64+'.csv'}
        stock = {'schema_version': 1, 'lots': [lot]}
        commit = 'b'*40
        identity = smoke_release_id(commit, stock)
        self.assertLessEqual(len(identity), 128)
        self.assertNotEqual(identity, smoke_release_id(commit, {'schema_version': 1, 'lots': [{**lot, 'generation': 2}]}))
        self.assertEqual(identity, smoke_release_id(commit, json.loads(json.dumps(stock))))
        self.assertEqual(smoke_release_id(commit, {'schema_version': 1, 'lots': []}), 'smoke-'+commit)

    def test_legacy_marker_fallback_only_on_missing_object(self):
        lot = {'generation': 1, 'rows': 1, 'sha256': 'a'*64, 'key': 'card-stock/'+'a'*64+'.csv'}
        manifest = {'fork_commit': 'b'*40, 'card_stock': {'schema_version': 1, 'lots': [lot]},
                    'release_id': 'test', 'gala_slug': 'gala-example',
                    **{name: 'image@sha256:'+'c'*64 for name in promotion.IMAGES}}
        for error, expected in (('404 Not Found', 2), ('AccessDenied', 1), ('network error', 1)):
            calls = []
            def run(command, **kwargs):
                if command[0] == 'aws':
                    calls.append(command)
                    if len(calls) == 1:
                        raise subprocess.CalledProcessError(1, command, stderr=error)
                    Path(command[5]).write_text(json.dumps(manifest))
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'release.json'; path.write_text(json.dumps(manifest))
                argv = ['validate-promotion', str(path), '--gala', 'gala-example', '--bucket', 'private', '--output', str(Path(directory)/'out.json')]
                with patch.object(sys, 'argv', argv), patch.object(subprocess, 'run', side_effect=run), \
                     patch.object(promotion, 'compare'), patch.object(subprocess, 'check_output', return_value='b'*40+'\n'):
                    if expected == 1:
                        with self.assertRaises(subprocess.CalledProcessError): promotion.main()
                    else:
                        promotion.main()
                        self.assertIn('test-validated/smoke-'+'b'*40+'.json', calls[-1][4])
                self.assertEqual(len(calls), expected)


if __name__ == '__main__':
    unittest.main()
