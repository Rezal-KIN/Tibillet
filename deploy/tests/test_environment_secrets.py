"""Shared integrations preserve each Gala's own credentials and isolation."""
import copy
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_gala_credentials import ROOT, generator, renderer, STRIPE_TEST, SHARED_MAIL

spec = importlib.util.spec_from_file_location('reconcile_runtime', ROOT / 'tools/runtime/reconcile-runtime.py')
reconciler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconciler)
PREFIX = 'arn:aws:secretsmanager:eu-west-3:318629836660:secret:tibillet-gala-paris/'
DOMAINS = ('fedow.galas-am-aix.rezal.fr', 'cashless.galas-am-aix.rezal.fr', 'galas-am-aix.rezal.fr')


def payload():
    return {
        'schema_version': 2, 'environment': 'dev',
        'stripe': copy.deepcopy(STRIPE_TEST['stripe']),
        'cawl': {'mode': 'test', **{key: 'example' for key in (
            'merchant_id', 'api_key_id', 'api_secret', 'webhook_key_id', 'webhook_secret')}},
        **{key: copy.deepcopy(value) for key, value in SHARED_MAIL.items() if key != 'schema_version'},
        'admin': {'username': 'admin', 'password_hash': 'pbkdf2_sha256$390000$sampleSalt$' + 'A' * 43 + '='},
    }


class EnvironmentSecretTests(unittest.TestCase):
    def test_common_integrations_render_identically_with_each_galas_own_keys(self):
        source = payload()
        payment, mail, admin = renderer.environment_sections(source, True)
        for provider in ('stripe', 'cawl'):
            first, second = generator.generated_payload(), generator.generated_payload()
            outputs = []
            for generated in (first, second):
                expected = renderer.assemble(generated, payment, SHARED_MAIL, *DOMAINS, True,
                                             admin_secret=source['admin'], require_admin=True, payment_provider=provider)
                actual = renderer.assemble(generated, payment, mail, *DOMAINS, True,
                                           admin_secret=admin, require_admin=True, payment_provider=provider)
                self.assertEqual(expected, actual)
                self.assertIn(generated['lespass_postgres_password'], actual['lespass.env'])
                outputs.append(actual)
            self.assertNotEqual(outputs[0]['lespass.env'], outputs[1]['lespass.env'])
            self.assertNotIn(second['lespass_postgres_password'], outputs[0]['lespass.env'])
            self.assertEqual(outputs[0]['admin.json'], outputs[1]['admin.json'])

    def test_common_object_rejects_gala_keys_and_wrong_environment(self):
        source = payload()
        for extra in ({'galas': {}}, {'lespass_postgres_password': 'sample'}):
            with self.assertRaisesRegex(ValueError, 'schema'):
                renderer.environment_sections({**source, **extra}, True)
        with self.assertRaisesRegex(ValueError, 'environment'):
            renderer.environment_sections(source, False)
        for provider in ('stripe', 'cawl'):
            changed = copy.deepcopy(source)
            changed[provider]['mode'] = 'live'
            with self.assertRaisesRegex(ValueError, 'mode'):
                renderer.environment_sections(changed, True)

    def test_production_integrations_and_empty_cawl_preserve_stripe(self):
        source = payload()
        source['environment'] = 'prod'
        source['stripe'].update(mode='live', secret_key='sk_live_example', publishable_key='pk_live_example')
        source['cawl'] = {key: 'live' if key == 'mode' else '' for key in source['cawl']}
        payment, mail, admin = renderer.environment_sections(source, False)
        generated = generator.generated_payload()
        files = renderer.assemble(generated, payment, mail, *DOMAINS, False,
                                  admin_secret=admin, require_admin=True, payment_provider='stripe')
        self.assertIn("STRIPE_KEY='sk_live_example'", files['fedow.env'])
        with self.assertRaises(ValueError):
            renderer.assemble(generated, payment, mail, *DOMAINS, False,
                              admin_secret=admin, require_admin=True, payment_provider='cawl')

    def test_host_config_requires_own_secret_and_correct_common_environment(self):
        own = PREFIX + 'galas/gala-smoke/generated-AbC123'
        shared = PREFIX + 'shared/integrations-stripe-test-AbC123'
        updated = reconciler.update('GALA_SLUG="gala-smoke"\n', 'gala-smoke', own, shared, shared)
        self.assertIn('GENERATED_SECRET_ARN="' + own + '"', updated)
        self.assertEqual(updated, reconciler.update(updated, 'gala-smoke', own, shared, shared))
        for generated in (shared, PREFIX + 'galas/gala-smoke-cawl/generated-AbC123'):
            with self.assertRaisesRegex(ValueError, 'own generated'):
                reconciler.update(updated, 'gala-smoke', generated, shared, shared)
        live = PREFIX + 'shared/integrations-stripe-live-AbC123'
        for payment, mail in ((live, live), (shared, live)):
            with self.assertRaises(ValueError):
                reconciler.update(updated, 'gala-smoke', own, payment, mail)

    def test_shell_reader_preserves_outputs_and_reads_only_own_and_common_secrets(self):
        source = payload()
        payment, mail, admin = renderer.environment_sections(source, True)
        for slug, provider in (('gala-smoke', 'stripe'), ('gala-smoke-cawl', 'cawl')):
            generated = generator.generated_payload()
            own = PREFIX + f'galas/{slug}/generated-AbC123'
            shared = PREFIX + 'shared/integrations-stripe-test-AbC123'
            legacy_mail = PREFIX + 'shared/integrations-mail-AbC123'
            expected = renderer.assemble(generated, payment, mail, *DOMAINS, True,
                                         admin_secret=admin, require_admin=True, payment_provider=provider)
            for legacy in (False, True):
                with self.subTest(slug=slug, legacy=legacy), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory)
                    fixtures = {
                        own + ':AWSCURRENT': generated,
                        shared + ':AWSCURRENT': payment if legacy else source,
                        legacy_mail + ':AWSCURRENT': mail,
                        legacy_mail + ':GALA_ADMIN': admin,
                    }
                    (path / 'fixtures.json').write_text(json.dumps(fixtures))
                    fake = path / 'aws'
                    fake.write_text('#!' + sys.executable + '\n' + """
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
name = args[args.index('--secret-id') + 1]
stage = args[args.index('--version-stage') + 1] if '--version-stage' in args else 'AWSCURRENT'
with open(os.environ['AWS_CALL_LOG'], 'a') as log:
    log.write(name + ':' + stage + '\\n')
values = json.loads(Path(os.environ['AWS_FIXTURES']).read_text())
if name + ':' + stage not in values:
    sys.exit(1)
print(json.dumps(values[name + ':' + stage]))
""")
                    fake.chmod(0o700)
                    config = {
                        'AWS_REGION': 'eu-west-3', 'BACKUP_BUCKET': 'example', 'REPO_ROOT': str(ROOT),
                        'RUNTIME_ROOT': str(path / 'runtime'), 'GALA_SLUG': slug,
                        'GENERATED_SECRET_ARN': own, 'SHARED_STRIPE_SECRET_ARN': shared,
                        'SHARED_MAIL_SECRET_ARN': legacy_mail if legacy else shared,
                        'PAYMENT_PROVIDER': provider,
                        'FEDOW_PUBLIC_DOMAIN': DOMAINS[0], 'LABOUTIK_PUBLIC_DOMAIN': DOMAINS[1],
                        'LESPASS_PUBLIC_DOMAIN': DOMAINS[2],
                    }
                    (path / 'gala.conf').write_text(''.join(key + '=' + shlex.quote(value) + '\n' for key, value in config.items()))
                    environment = {**os.environ, 'PATH': str(path) + os.pathsep + os.environ['PATH'],
                                   'AWS_FIXTURES': str(path / 'fixtures.json'), 'AWS_CALL_LOG': str(path / 'calls')}
                    result = subprocess.run(['bash', str(ROOT / 'tools/runtime/fetch-runtime-secret.sh'), str(path / 'gala.conf')],
                                            env=environment, text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    runtime = path / 'runtime' / slug
                    self.assertEqual({file.name for file in runtime.iterdir()}, set(expected))
                    for filename, contents in expected.items():
                        self.assertEqual((runtime / filename).read_text(), contents)
                    calls = (path / 'calls').read_text().splitlines()
                    expected_calls = [own + ':AWSCURRENT', shared + ':AWSCURRENT']
                    if legacy:
                        expected_calls += [legacy_mail + ':AWSCURRENT', legacy_mail + ':GALA_ADMIN']
                    self.assertEqual(calls, expected_calls)
                    self.assertNotIn(generated['lespass_postgres_password'], result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
