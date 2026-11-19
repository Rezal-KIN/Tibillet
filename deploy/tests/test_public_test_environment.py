"""A public test migration may not replace production or widen its scope."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

from test_validate_foundation_inputs import run

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_test_plan', ROOT / 'tools/verify-foundation-plan.py')
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)
OLD = 'galas-am-aix.rezal.fr'
NEW = 'gala-test.rezal.fr'
SMOKE = 'gala-smoke-cawl'
HOST = 'i-0123456789abcdef0'


def catalogue():
    entry = {'platform': 'v1', 'domain': OLD, 'instance_type': 't3.medium',
             'root_volume_size_gib': 40, 'ssh_emergency_cidrs': [],
             'associate_public_ip_address': True, 'create_instance': True,
             'protect_from_destruction': True}
    return {'version': 1, 'galas': {
        'gala-smoke': entry.copy(), SMOKE: {**entry, 'payment_provider': 'cawl'},
        'bapts2026': {**entry, 'payment_provider': 'cawl'},
    }}


def document(slug, provider):
    command = f'python3 "$repo/deploy/tools/runtime/reconcile-runtime.py" /etc/tibillet-gala/{slug}.conf {slug} generated payment mail'
    if provider == 'cawl':
        command += ' cawl'
    old = {'schemaVersion': '2.2', 'mainSteps': [{'inputs': {'runCommand': ['set -eu', command, 'deploy-fixed-manifest']}}]}
    domain = NEW if slug in {'gala-smoke', SMOKE} else OLD
    new = copy.deepcopy(old)
    new['mainSteps'][0]['inputs']['runCommand'][1] = command + (
        f" '{domain}'" if provider == 'cawl' else f" stripe '{domain}'")
    return {'address': f'aws_ssm_document.production_deploy["{slug}"]',
            'change': {'actions': ['update'],
                       'before': {'name': slug, 'content': json.dumps(old)},
                       'after': {'name': slug, 'content': json.dumps(new)},
                       'after_unknown': {}}}


def public_plan():
    group = {'id': 'sg-0123456789abcdef0', 'tags': {'Gala': SMOKE}, 'ingress': [], 'egress': []}
    rules = [{'description': 'Independent CAWL test HTTP/HTTPS', 'from_port': p, 'to_port': p,
              'protocol': 'tcp', 'cidr_blocks': ['0.0.0.0/0'], 'ipv6_cidr_blocks': [],
              'prefix_list_ids': [], 'security_groups': [], 'self': False} for p in [80, 443]]
    return {'resource_changes': [
        {'address': f'module.gala["{SMOKE}"].aws_instance.runtime[0]',
         'change': {'actions': ['no-op'], 'before': {'id': HOST}, 'after': {'id': HOST}}},
        {'address': 'aws_eip_association.cawl_test_public[0]', 'change': {'actions': ['create'], 'after': {
            'instance_id': HOST, 'allocation_id': 'eipalloc-0123456789abcdef0', 'allow_reassociation': False}}},
        {'address': f'module.gala["{SMOKE}"].aws_security_group.runtime', 'change': {
            'actions': ['update'], 'before': group, 'after': {**group, 'ingress': rules}, 'after_unknown': {}}},
        document(SMOKE, 'cawl'), document('bapts2026', 'cawl'),
        {'address': 'aws_eip.cawl_test_public[0]', 'change': {'actions': ['no-op'], 'before': {
            'id': 'eipalloc-0123456789abcdef0', 'tags': {'Name': 'tibillet-gala-paris-cawl-test-public'}}}},
    ]}


class PublicTestTests(unittest.TestCase):
    def test_catalogue_changes_only_smoke_domains_and_remembers_the_mode(self):
        before = catalogue()
        result, output, reserved = run(before, GALA_NAME='Reserve CAWL Test Address')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(reserved['galas'], before['galas'])
        self.assertTrue(output['reserve_cawl_test_address'])
        self.assertFalse(output['enable_public_cawl_test'])
        result, output, after = run(reserved, GALA_NAME='Enable Public CAWL Test')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output['enable_public_cawl_test'])
        self.assertTrue(after['public_cawl_test_enabled'])
        self.assertEqual(after['galas']['bapts2026'], before['galas']['bapts2026'])
        self.assertEqual(after['galas']['gala-smoke'], before['galas']['gala-smoke'])
        self.assertEqual(after['galas'][SMOKE], {**before['galas'][SMOKE], 'domain': NEW})
        result, output, preserved = run(after, GALA_NAME='Gala Next', PAYMENT_PROVIDER='cawl')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output['enable_public_cawl_test'])
        self.assertEqual(preserved['galas'][SMOKE], after['galas'][SMOKE])
        self.assertEqual(preserved['galas']['gala-next']['domain'], OLD)

    def test_unknown_domains_and_missing_or_wrong_provider_hosts_are_refused(self):
        original = {**catalogue(), 'public_cawl_test_address_reserved': True}
        bad = copy.deepcopy(original);bad['galas'][SMOKE]['domain'] = 'other.example.org'
        self.assertNotEqual(run(bad, GALA_NAME='Enable Public CAWL Test')[0].returncode, 0)
        bad = copy.deepcopy(original);del bad['galas'][SMOKE]
        self.assertNotEqual(run(bad, GALA_NAME='Enable Public CAWL Test')[0].returncode, 0)
        bad = copy.deepcopy(original);bad['galas'][SMOKE]['payment_provider'] = 'stripe'
        self.assertNotEqual(run(bad, GALA_NAME='Enable Public CAWL Test')[0].returncode, 0)
        self.assertNotEqual(run(catalogue(), GALA_NAME='Enable Public CAWL Test', PAYMENT_PROVIDER='cawl')[0].returncode, 0)
        self.assertNotEqual(run(catalogue(), GALA_NAME='Enable Public CAWL Test')[0].returncode, 0)

    def test_reservation_cannot_associate_an_address_or_change_another_resource(self):
        item = {'address': 'aws_eip.cawl_test_public[0]', 'change': {'actions': ['create'], 'after': {
            'domain': 'vpc', 'tags': {'Name': 'tibillet-gala-paris-cawl-test-public', 'Project': 'tibillet-gala-paris'}}}}
        configuration = {'root_module': {'resources': [{'address': 'aws_eip.cawl_test_public',
                         'expressions': {'domain': {'constant_value': 'vpc'}, 'tags': {'references': ['local.common_tags']}}}]}}
        item['change']['after_unknown'] = {'instance': True, 'network_interface': True}
        self.assertEqual(plan.verify_test_address_plan({'resource_changes': [item], 'configuration': configuration}), ['reserve-unassociated-test-address'])
        for mutate in [lambda v: v['change']['after'].update(instance=HOST),
                       lambda v: v.update(address='aws_eip.shared_public[0]'),
                       lambda v: v['change'].update(actions=['delete'])]:
            bad = copy.deepcopy(item);mutate(bad)
            with self.assertRaises(ValueError):
                plan.verify_test_address_plan({'resource_changes': [bad], 'configuration': configuration})
        for key in ['instance', 'network_interface']:
            bad = copy.deepcopy(configuration)
            bad['root_module']['resources'][0]['expressions'][key] = {'references': ['aws_instance.unexpected.id']}
            with self.subTest(key=key), self.assertRaises(ValueError):
                plan.verify_test_address_plan({'resource_changes': [item], 'configuration': bad})

    def test_exact_existing_host_http_https_and_domain_only_change_are_accepted(self):
        self.assertEqual(len(plan.verify_public_test_plan(public_plan())), 4)
        bad = public_plan();bad['resource_changes'].append(document('gala-smoke', 'stripe'))
        with self.assertRaises(ValueError):
            plan.verify_public_test_plan(bad)

    def test_production_mutations_and_wider_ingress_or_commands_are_refused(self):
        mutations = [
            lambda v: v['resource_changes'][1]['change']['after'].update(instance_id='i-other'),
            lambda v: v['resource_changes'][1].update(address='aws_eip.shared_public[0]'),
            lambda v: v['resource_changes'][0]['change'].update(actions=['delete', 'create']),
            lambda v: v['resource_changes'][2]['change']['after']['ingress'][0].update(from_port=22),
            lambda v: v['resource_changes'][2]['change']['after'].update(egress=[{'protocol': '-1'}]),
            lambda v: v['resource_changes'][2]['change'].update(after_unknown={'ingress': True}),
        ]
        for mutate in mutations:
            bad = public_plan();mutate(bad)
            with self.assertRaises(ValueError):
                plan.verify_public_test_plan(bad)
        for slug, provider in [(SMOKE, 'cawl'), ('bapts2026', 'cawl')]:
            item = document(slug, provider)
            for change in [lambda d: d['mainSteps'][0]['inputs']['runCommand'].append('unexpected-command'),
                           lambda d: d['mainSteps'][0]['inputs']['runCommand'].__setitem__(1, 'python3 unexpected-script')]:
                bad = copy.deepcopy(item)
                content = json.loads(bad['change']['after']['content']);change(content)
                bad['change']['after']['content'] = json.dumps(content)
                self.assertFalse(plan.safe_public_test_document(bad['change'], slug))


if __name__ == '__main__':
    unittest.main()
