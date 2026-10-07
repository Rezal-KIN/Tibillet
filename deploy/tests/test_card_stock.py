"""Private catalogue contract and real pinned Fedow importer on SQLite."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'tools/runtime'
sys.path.insert(0, str(RUNTIME))
import card_stock as stock


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


host = load('card_stock_host', RUNTIME / 'import-gala-card-stock.py')
publisher = load('card_stock_publisher', ROOT / 'tools/publish-card-stock.py')
smoke = load('card_stock_smoke', ROOT / 'tools/create-smoke-manifest.py')
promotion = load('card_stock_promotion', ROOT / 'tools/validate-promotion.py')
foundation = load('card_stock_foundation', ROOT / 'tools/verify-foundation-plan.py')
DOMAIN = 'galas-am-aix.rezal.fr'
CSV = f'https://{DOMAIN}/qr/11111111-1111-4111-8111-111111111111,11111111,AABBCCDD\n'.encode()
LOT = {'sha256': hashlib.sha256(CSV).hexdigest(), 'rows': 1, 'generation': 1}
LOT['key'] = f"card-stock/{LOT['sha256']}.csv"
CATALOGUE = {'schema_version': 1, 'lots': [LOT]}


class CardStockContractTests(unittest.TestCase):
    def test_embedded_deploy_buildspec_supports_old_and_stock_source_revisions(self):
        buildspec = (ROOT / 'buildspec/tibillet-test-deploy.yml').read_text()
        command = buildspec.split('      - |\n', 1)[1].split('      - python3', 1)[0]
        command = '\n'.join(line[8:] for line in command.splitlines())
        candidate = {'application_repository': 'Rezal-KIN/Tibillet', 'fork_commit': 'a' * 40,
                     'platform': 'v1', 'lespass_image': 'image@sha256:' + 'a' * 64}
        images = {'schema_version': 1, **{key: 'image@sha256:' + 'b' * 64
            for key in ('fedow_image', 'laboutik_image', 'traefik_image')}}
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / 'deploy/tools').mkdir(parents=True)
            (repo / 'build').mkdir()
            (repo / 'build/release-candidate.json').write_text(json.dumps(candidate))
            (repo / 'deploy/test-images.json').write_text(json.dumps(images))
            output = repo / 'manifest.json'
            script = command.replace('/tmp/smoke-manifest.json', str(output))
            env = {**os.environ, 'CODEBUILD_SRC_DIR_BuildOutput': str(repo / 'build')}
            # The legacy contract has exactly three positional arguments and
            # rejects the new flag, just like the previous manifest CLI.
            (repo / 'deploy/tools/create-smoke-manifest.py').write_text(
                'import argparse,json\np=argparse.ArgumentParser()\n'
                "p.add_argument('candidate');p.add_argument('images');p.add_argument('output')\n"
                "a=p.parse_args();open(a.output,'w').write(json.dumps({'legacy':True}))\n")
            old = subprocess.run(['bash', '-euc', script], cwd=repo, env=env,
                                 text=True, capture_output=True)
            self.assertEqual(old.returncode, 0, old.stderr)
            self.assertEqual(json.loads(output.read_text()), {'legacy': True})
            shutil.copyfile(ROOT / 'tools/create-smoke-manifest.py', repo / 'deploy/tools/create-smoke-manifest.py')
            (repo / 'deploy/tools/runtime').mkdir()
            shutil.copyfile(RUNTIME / 'card_stock.py', repo / 'deploy/tools/runtime/card_stock.py')
            (repo / 'deploy/card-stock.json').write_text(json.dumps(CATALOGUE))
            current = subprocess.run(['bash', '-euc', script], cwd=repo, env=env,
                                     text=True, capture_output=True)
            self.assertEqual(current.returncode, 0, current.stderr)
            self.assertEqual(json.loads(output.read_text())['card_stock'], CATALOGUE)

    def test_validates_real_csv_bytes_and_rejects_corruption(self):
        cards = stock.verified_cards(CSV, LOT, DOMAIN)
        self.assertEqual(len(cards), 1)
        for data, lot in ((CSV + b'\n', LOT), (CSV, {**LOT, 'rows': 2})):
            with self.subTest(data=data), self.assertRaises(ValueError):
                stock.verified_cards(data, lot, DOMAIN)

    def test_refuses_header_invalid_fields_and_duplicates_across_lots(self):
        for data in (b'QR,NUMBER,NFC\n', CSV.replace(b'AABBCCDD', b'123'),
                     CSV.replace(b'AABBCCDD', b'aabbccdd'), CSV + CSV,
                     CSV.replace(b'/qr/', b'/qrcode/'),
                     CSV.replace(DOMAIN.encode(), b'other.example.org'),
                     CSV.replace(b'11111111,A', b'11111111/,A')):
            with self.subTest(data=data), self.assertRaises(ValueError):
                stock.read_cards(data, DOMAIN)
        cards = stock.read_cards(CSV, DOMAIN)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            stock.validate_unique([{'cards': cards}, {'cards': cards}])

    def test_refuses_mutable_keys_counts_types_and_extra_stock_data(self):
        for changes in ({'key': 'card-stock/latest.csv'}, {'key': '../secret.csv'},
                        {'rows': True}, {'generation': 0}, {'generation': True},
                        {'sha256': 'a' * 63}, {'cards': []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                stock.validate_catalogue({'schema_version': 1, 'lots': [{**LOT, **changes}]})
        with self.assertRaises(ValueError):
            stock.validate_catalogue({'schema_version': True, 'lots': []})
        with self.assertRaises(ValueError):
            stock.validate_catalogue({'schema_version': 1, 'lots': [LOT, LOT]})

    def test_download_verifies_all_lots_and_cleans_temporary_files(self):
        destinations = []
        def download(command, **kwargs):
            self.assertIn(f"s3://private-stock/{LOT['key']}", command)
            path = Path(command[5])
            destinations.append(path)
            path.write_bytes(CSV)
        with patch.object(host.subprocess, 'run', side_effect=download):
            lots = host.load_lots(CATALOGUE, 'private-stock', 'eu-west-3', DOMAIN)
        self.assertEqual(lots[0]['cards'], stock.read_cards(CSV, DOMAIN))
        self.assertTrue(all(not path.exists() for path in destinations))
        def corrupted(command, **kwargs):
            Path(command[5]).write_bytes(b'corrupted')
        with patch.object(host.subprocess, 'run', side_effect=corrupted), self.assertRaises(ValueError):
            host.load_lots(CATALOGUE, 'private-stock', 'eu-west-3', DOMAIN)

    def test_publication_never_overwrites_an_existing_object(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lot.csv'
            path.write_bytes(CSV)
            def prior(command, **kwargs):
                if 'put-object' in command:
                    self.assertIn('--if-none-match', command)
                    return subprocess.CompletedProcess(command, 1, '', 'PreconditionFailed')
                Path(command[-1]).write_bytes(CSV)
                return subprocess.CompletedProcess(command, 0)
            with patch.object(publisher.subprocess, 'run', side_effect=prior):
                publisher.publish(['aws'], 'private-stock', LOT, path)
            def conflicting(command, **kwargs):
                result = prior(command, **kwargs)
                if 'put-object' not in command:
                    Path(command[-1]).write_bytes(b'different')
                return result
            with patch.object(publisher.subprocess, 'run', side_effect=conflicting), self.assertRaises(ValueError):
                publisher.publish(['aws'], 'private-stock', LOT, path)

    def test_promotion_requires_exact_smoke_stock_and_keeps_old_manifests_valid(self):
        candidate = {'application_repository': 'Rezal-KIN/Tibillet', 'fork_commit': 'a' * 40,
                     'platform': 'v1', 'lespass_image': 'image@sha256:' + 'a' * 64}
        images = {'schema_version': 1, **{key: 'image@sha256:' + 'b' * 64
            for key in ('fedow_image', 'laboutik_image', 'traefik_image')}}
        tested = smoke.create(candidate, images, CATALOGUE)
        self.assertEqual(tested['card_stock'], CATALOGUE)
        production = {**tested, 'gala_slug': 'gala-am-aix'}
        promotion.compare(production, tested, 'gala-am-aix')
        for modified in (stock.EMPTY_STOCK, {'schema_version': 1, 'lots': [{**LOT, 'generation': 2}]}):
            with self.assertRaisesRegex(ValueError, 'card_stock differs'):
                promotion.compare({**production, 'card_stock': modified}, tested, 'gala-am-aix')
        old = {key: value for key, value in tested.items() if key != 'card_stock'}
        promotion.compare({**old, 'gala_slug': 'gala-am-aix'}, old, 'gala-am-aix')

    def test_install_and_deployment_use_temporary_input_without_new_compose_mount(self):
        installer = (RUNTIME / 'install-runtime-contract.sh').read_text()
        scripts = installer.split('for script in', 1)[1].split('; do', 1)[0].split()
        for name in ('card_stock.py', 'import_card_stock_fedow.py', 'import-gala-card-stock.py'):
            self.assertIn(name, scripts)
        release = (RUNTIME / 'deploy-release.sh').read_text()
        self.assertLess(release.index('manage.py install\'' , release.index('laboutik_django bash')),
                        release.index('import-gala-card-stock.py'))
        self.assertLess(release.index('import-gala-card-stock.py'), release.index('healthy=false'))
        for path in ROOT.glob('*/docker-compose*.yml'):
            self.assertNotIn('card-stock', path.read_text())

    def test_validated_artifact_contains_every_validator_dependency(self):
        # Production consumes this artifact only; it does not check out source.
        buildspec = (ROOT / 'buildspec/tibillet-production-validate.yml').read_text()
        files = [line.strip()[2:] for line in buildspec.split('artifacts:', 1)[1].splitlines()
                 if line.strip().startswith('- ')]
        release = {'release_id': 'test-stock', 'gala_slug': 'gala-example', 'platform': 'v1',
            'application_repository': 'Rezal-KIN/Tibillet', 'fork_commit': 'a' * 40,
            'tibillet_upstream_commit': 'a' * 40, 'schema_generation': 'v1', 'card_stock': CATALOGUE,
            **{field: 'image@sha256:' + 'a' * 64 for field in promotion.IMAGES}}
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory)
            for name in files:
                destination = artifact / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if name == 'validated-manifest.json':
                    destination.write_text(json.dumps(release))
                else:
                    shutil.copyfile(ROOT.parent / name, destination)
            result = subprocess.run([sys.executable, str(artifact / 'deploy/tools/runtime/validate-release.py'),
                                     str(artifact / 'validated-manifest.json')], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_foundation_updates_only_embedded_buildspecs_with_identity_preserved(self):
        for address in ('aws_codebuild_project.test_deploy[0]',
                        'aws_codebuild_project.production_validate["gala-am-aix"]'):
            before = {'name': 'unchanged', 'service_role': 'same-role', 'build_timeout': 15,
                      'source': [{'type': 'CODEPIPELINE', 'buildspec': 'old'}]}
            after = {**before, 'source': [{'type': 'CODEPIPELINE', 'buildspec': 'new'}]}
            change = {'actions': ['update'], 'before': before, 'after': after, 'after_unknown': {}}
            plan = {'resource_changes': [{'address': address, 'change': change}]}
            self.assertEqual(len(foundation.verify(plan, 'gala-example')), 1)
            for key, value in (('service_role', '*'), ('name', 'another'), ('build_timeout', 60)):
                bad = copy.deepcopy(plan)
                bad['resource_changes'][0]['change']['after'][key] = value
                with self.assertRaises(ValueError):
                    foundation.verify(bad, 'gala-example')

    def test_foundation_permits_only_the_precise_private_read_addition(self):
        resource = 'arn:aws:s3:::private-gala/releases/gala-smoke/*'
        old = {'Version': '2012-10-17', 'Statement': [
            {'Sid': 'ReadOnlyOwnReleaseManifests', 'Effect': 'Allow', 'Action': 's3:GetObject', 'Resource': resource}]}
        new = copy.deepcopy(old)
        new['Statement'].append({'Sid': 'ReadOnlySharedCardStock', 'Effect': 'Allow',
            'Action': 's3:GetObject', 'Resource': 'arn:aws:s3:::private-gala/card-stock/*'})
        change = {'actions': ['update'], 'after_unknown': {},
                  'before': {'id': 'unchanged', 'policy': json.dumps(old)},
                  'after': {'id': 'unchanged', 'policy': json.dumps(new)}}
        address = 'module.gala["gala-smoke"].aws_iam_role_policy.runtime'
        plan = {'resource_changes': [{'address': address, 'change': change}]}
        self.assertEqual(foundation.verify(plan, 'gala-smoke'), ['allow-shared-card-stock-read ' + address])
        for field, value in (('Action', 's3:PutObject'), ('Resource', '*'),
                             ('Resource', 'arn:aws:s3:::other/card-stock/*')):
            bad = copy.deepcopy(change)
            policy = copy.deepcopy(new)
            policy['Statement'][-1][field] = value
            bad['after']['policy'] = json.dumps(policy)
            self.assertFalse(foundation.safe_card_stock_read_addition(bad, address))


class NativeCardStockTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('django'), 'requires Django for the native SQLite regression')
    def test_native_fresh_repeat_partial_conflict_and_rollback_preserve_accounts(self):
        # Reuse the checksum-verified source archive; never vendor/rewrite the
        # native command under test, or depend on a gitignored investigation.
        offer = load('card_stock_source_offer', ROOT / 'tools/build-source-offer.py')
        reference = json.loads((ROOT / 'source/image-sources.json').read_text())['fedow']
        source = offer.upstream_source(reference, ROOT.parent / '.context/source-cache')
        native = source['fedow_core/management/commands/import_cards.py'][0]
        self.assertEqual(hashlib.sha256(native).hexdigest(),
                         'cf1217b46eacd7f8e85ef71c6c5e6df79ec6e03baeb422030e38dabc001c30a6')
        probe = r'''
import contextlib, importlib.util, io, json, sys, types
from unittest.mock import patch
from uuid import uuid4
from django.conf import settings
settings.configure(SECRET_KEY='isolated-card-stock-test', INSTALLED_APPS=[],
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}})
import django
django.setup()
from django.db import connection, models
from django.db.models.signals import post_save
class Place(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    wallet_id = models.UUIDField(default=uuid4)
    name = models.CharField(max_length=100)
    lespass_domain = models.CharField(max_length=100)
    class Meta: app_label = 'fedow_core'
class Origin(models.Model):
    place = models.ForeignKey(Place, on_delete=models.PROTECT)
    generation = models.IntegerField()
    class Meta: app_label = 'fedow_core'
class Wallet(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    balance = models.IntegerField(default=0)
    class Meta: app_label = 'fedow_core'
class User(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT)
    class Meta: app_label = 'fedow_core'
class Card(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    first_tag_id = models.CharField(max_length=8, unique=True)
    qrcode_uuid = models.UUIDField(unique=True)
    number_printed = models.CharField(max_length=8, unique=True)
    origin = models.ForeignKey(Origin, on_delete=models.PROTECT)
    user = models.ForeignKey(User, null=True, on_delete=models.PROTECT)
    wallet_ephemere = models.OneToOneField(Wallet, null=True, on_delete=models.PROTECT)
    class Meta: app_label = 'fedow_core'
with connection.schema_editor() as schema:
    for model in (Place, Origin, Wallet, User, Card): schema.create_model(model)
sys.modules['fedow_core.models'] = types.SimpleNamespace(Place=Place, Card=Card, Origin=Origin)
native = types.ModuleType('native_import_cards')
exec(open(sys.argv[2]).read(), native.__dict__)
spec = importlib.util.spec_from_file_location('stock_worker', sys.argv[1])
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
from django.core.management import get_commands
get_commands()['import_cards'] = 'fedow_core'
domain = 'galas-am-aix.rezal.fr'
peer = Place.objects.create(name='Other', lespass_domain=domain)
place = Place.objects.create(name='Festival', lespass_domain=domain)
identity = {'place_uuid': str(place.pk), 'wallet_uuid': str(place.wallet_id)}
def row(n): return (f'https://{domain}/qr/{uuid4()}', f'{n:08d}', f'{n+1000:08X}')
cards = [row(n) for n in range(225)]
lots = [{'generation': 1, 'cards': cards[:220]}, {'generation': 2, 'cards': cards[220:]}]
def run(target=lots, check=False, pairing=identity):
    with patch('django.core.management.load_command_class', return_value=native.Command()):
        return worker.import_stock(pairing, domain, target, check=check)
def fails(fn):
    try: fn()
    except Exception: return
    raise AssertionError('expected rejection')
fails(lambda: run(check=True))
assert Card.objects.count() == 0 and Origin.objects.count() == 0
receipt = run()
assert receipt['created'] == 225 and receipt['existing'] == 0
assert set(Card.objects.values_list('origin__place_id', flat=True)) == {place.pk}
assert Wallet.objects.count() == 0 and User.objects.count() == 0
card = Card.objects.first()
wallet = Wallet.objects.create(balance=12345)
user = User.objects.create(wallet=wallet)
card.user = user; card.save()
before = list(Card.objects.order_by('uuid').values())
writes = []
post_save.connect(lambda **kwargs: writes.append(kwargs['instance'].pk), sender=Card, weak=False)
assert run()['created'] == 0 and run(check=True)['existing'] == 225
assert writes == [] and before == list(Card.objects.order_by('uuid').values())
assert Wallet.objects.get(pk=wallet.pk).balance == 12345 and User.objects.count() == 1
# Missing subset: preserve existing card IDs/links, import only the deleted one.
deleted = Card.objects.exclude(pk=card.pk).last(); deleted.delete()
assert run()['created'] == 1 and Card.objects.count() == 225
card.refresh_from_db(); assert card.user_id == user.pk
# New stock, with no effect on earlier generations.
extra = {'generation': 3, 'cards': [row(999)]}
assert run(lots + [extra])['created'] == 1
assert Wallet.objects.get(pk=wallet.pk).balance == 12345
# Partial and crossed associations: detect the conflict before importing the
# entirely absent row earlier in the catalogue.
for conflict in [(row(1234)[0], card.number_printed, 'ABCDEF12'),
                 (f'https://{domain}/qr/{card.qrcode_uuid}', 'NOCHANGE', 'ABCDEF12'),
                 (row(1234)[0], 'NOCHANGE', card.first_tag_id)]:
    count = Card.objects.count(); origins = Origin.objects.count()
    fails(lambda: run([{'generation': 9, 'cards': [row(8888)]},
                       {'generation': 10, 'cards': [conflict]}]))
    assert Card.objects.count() == count and Origin.objects.count() == origins
# A failure during a later lot rolls back earlier native imports and origins.
count = Card.objects.count(); origins = Origin.objects.count()
real_call = worker.call_command
calls = []
def interrupted(*args, **kwargs):
    calls.append(1)
    if len(calls) == 2: raise RuntimeError('simulated interruption')
    return real_call(*args, **kwargs)
pending = [{'generation': 20, 'cards': [row(4444)]}, {'generation': 21, 'cards': [row(4445)]}]
with patch.object(worker, 'call_command', interrupted): fails(lambda: run(pending))
assert len(calls) == 2 and Card.objects.count() == count and Origin.objects.count() == origins
assert run(pending)['created'] == 2
# Native index ordering changed between discovery and invocation: postcheck
# must roll back an otherwise successful native import into the wrong place.
count = Card.objects.count(); origins = Origin.objects.count()
def wrong_origin(*args, **kwargs):
    import builtins
    original = builtins.input
    with patch('builtins.input', lambda prompt: '0' if prompt == '\nnumber ? \n' else original(prompt)):
        return real_call(*args, **kwargs)
with patch.object(worker, 'call_command', wrong_origin):
    fails(lambda: run([{'generation': 30, 'cards': [row(5555)]}]))
assert Card.objects.count() == count and Origin.objects.count() == origins
fails(lambda: run(pairing={**identity, 'wallet_uuid': str(uuid4())}))
Place.objects.create(name=place.name, lespass_domain=domain)
fails(lambda: run())
assert Wallet.objects.get(pk=wallet.pk).balance == 12345
'''
        with tempfile.TemporaryDirectory() as directory:
            native_path = Path(directory) / 'native_import_cards.py'
            native_path.write_bytes(native)
            result = subprocess.run([sys.executable, '-c', probe,
                                     str(RUNTIME / 'import_card_stock_fedow.py'), str(native_path)],
                                    capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
