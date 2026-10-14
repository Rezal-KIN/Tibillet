"""Retirement is restricted to the user-approved Paris Bapts test instance."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from test_validate_foundation_inputs import run
from test_verify_foundation_plan import module as plans
from test_verify_gala_bootstrap import module as bootstrap

spec = importlib.util.spec_from_file_location('park_bapts', Path(__file__).parents[1] / 'tools/park-bapts-retirement.py')
park = importlib.util.module_from_spec(spec)
spec.loader.exec_module(park)
SLUG = 'baldubapts2026'


def trial(phase):
    before = {'id': park.INSTANCE, 'primary_network_interface_id': 'eni-0123456789abcdef0',
              'disable_api_termination': phase == 'prepare',
              'tags': {'Project': 'tibillet-gala-paris', 'Gala': SLUG, 'ManagedBy': 'terraform'},
              'root_block_device': [{'volume_id': park.VOLUME, 'volume_size': 40,
                                     'delete_on_termination': phase != 'prepare'}]}
    after = copy.deepcopy(before) if phase == 'prepare' else None
    if after:
        after['disable_api_termination'] = False
        after['root_block_device'][0]['delete_on_termination'] = True
    return {'resource_changes': [{'address': f'module.gala["{SLUG}"].aws_instance.retirable[0]',
                                 'change': {'actions': ['update' if after else 'delete'],
                                            'before': before, 'after': after, 'after_unknown': {}}}]}


class BaptsRetirementTests(unittest.TestCase):
    def test_catalog_requires_preparation_and_preserves_other_galas(self):
        gala = {'platform': 'v1', 'domain': 'galas-am-aix.rezal.fr', 'instance_type': 't3.medium',
                'root_volume_size_gib': 40, 'ssh_emergency_cidrs': [], 'associate_public_ip_address': True,
                'create_instance': True, 'protect_from_destruction': True}
        catalog = {'version': 1, 'galas': {SLUG: dict(gala), 'gala-smoke': dict(gala)}}
        result, _, _ = run(catalog, GALA_NAME='Retire BalduBapts2026')
        self.assertNotEqual(result.returncode, 0)
        result, _, _ = run(catalog, GALA_NAME='Enable CAWL Platform')
        self.assertNotEqual(result.returncode, 0)
        result, _, prepared = run(catalog, GALA_NAME='Prepare BalduBapts2026 Retirement')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(prepared['galas'][SLUG]['protect_from_destruction'])
        self.assertEqual(prepared['galas']['gala-smoke'], gala)
        result, _, retired = run(prepared, GALA_NAME='Retire BalduBapts2026')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(retired['galas'][SLUG]['create_instance'])
        self.assertEqual(set(retired['galas']), set(catalog['galas']))
        self.assertEqual(retired['galas']['gala-smoke'], gala)

    def test_plan_rejects_other_instances_or_volumes(self):
        for phase in ('prepare', 'retire'):
            plan = trial(phase)
            self.assertEqual(len(plans.verify_verification_retirement_plan(plan, phase, slug=SLUG)), 1)
            for key in ('id', 'volume_id'):
                invalid = copy.deepcopy(plan)
                before = invalid['resource_changes'][0]['change']['before']
                if key == 'id': before['id'] = 'i-00000000000000000'
                else: before['root_block_device'][0]['volume_id'] = 'vol-00000000000000000'
                with self.assertRaises(ValueError):
                    plans.verify_verification_retirement_plan(invalid, phase, slug=SLUG)
            plan['resource_changes'].append({'address': 'module.gala["gala-smoke"].aws_instance.runtime[0]',
                                             'change': {'actions': ['delete'], 'before': {}, 'after': None}})
            with self.assertRaises(ValueError):
                plans.verify_verification_retirement_plan(plan, phase, slug=SLUG)

    def test_cawl_smoke_policy_refresh_preserves_identity_and_permissions(self):
        plan = trial('retire')
        before = {'id': 'existing', 'name': 'cawl-smoke-policy', 'role': 'cawl-smoke-role', 'policy': '{}'}
        item = {'address': 'aws_iam_role_policy.test_cawl_deploy[0]',
                'change': {'actions': ['update'], 'before': before,
                           'after': {**before, 'policy': None}, 'after_unknown': {'policy': True}}}
        plan['resource_changes'].append(item)
        self.assertEqual(len(plans.verify_verification_retirement_plan(plan, 'retire', slug=SLUG)), 2)
        for update in ({'role': 'another-role'}, {'policy': '{"Statement": []}'}):
            invalid = copy.deepcopy(plan)
            invalid['resource_changes'][-1]['change']['after'].update(update)
            with self.assertRaises(ValueError):
                plans.verify_verification_retirement_plan(invalid, 'retire', slug=SLUG)

    def responder(self, *args):
        if args[:2] == ('sts', 'get-caller-identity'): return {'Account': park.ACCOUNT}
        if args[:2] == ('ec2', 'describe-instances'):
            return {'Reservations': [{'Instances': [{'State': {'Name': 'stopped'},
                'Tags': [{'Key': k, 'Value': v} for k, v in {'Project': 'tibillet-gala-paris', 'Gala': SLUG, 'ManagedBy': 'terraform'}.items()],
                'BlockDeviceMappings': [{'Ebs': {'VolumeId': park.VOLUME}}]}]}]}
        if args[:2] == ('ec2', 'describe-snapshots'):
            return {'Snapshots': [{'State': 'completed', 'OwnerId': park.ACCOUNT, 'VolumeId': park.VOLUME, 'Encrypted': True}]}
        if args[:2] == ('ec2', 'describe-addresses'):
            return {'Addresses': [{'InstanceId': park.INSTANCE, 'AssociationId': 'eipassoc-test', 'PublicIp': '51.44.90.200'}]}
        if args[:2] == ('ssm', 'get-parameter'): return {'Parameter': {'Value': SLUG}}
        raise AssertionError(args)

    def test_parking_defaults_to_read_only_and_checks_real_dns(self):
        with patch.object(park, 'aws', side_effect=self.responder) as aws, \
             patch.object(park.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('13.48.235.148', 443))]), \
             patch.object(sys, 'argv', ['park']):
            park.main()
            self.assertTrue(all(call.args[1].startswith(('describe-', 'get-')) for call in aws.call_args_list))
        with patch.object(park, 'aws', side_effect=self.responder), \
             patch.object(park.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('51.44.90.200', 443))]), \
             self.assertRaisesRegex(ValueError, 'DNS'):
            park.inspect()

    def test_incomplete_archive_and_another_active_gala_are_refused(self):
        for kind in ('snapshot', 'active'):
            def invalid(*args):
                result = self.responder(*args)
                if kind == 'snapshot' and args[:2] == ('ec2', 'describe-snapshots'): result['Snapshots'][0]['State'] = 'pending'
                if kind == 'active' and args[:2] == ('ssm', 'get-parameter'): result['Parameter']['Value'] = 'gala-smoke'
                return result
            with patch.object(park, 'aws', side_effect=invalid), self.assertRaises(ValueError):
                park.inspect()
        with patch.object(bootstrap, 'aws', return_value={'Parameter': {'Value': SLUG}}), self.assertRaises(RuntimeError):
            bootstrap.verify_validation_retirement(trial('retire'), 'retire', 'tibillet-gala-paris', targets=(SLUG,))


if __name__ == '__main__':
    unittest.main()
