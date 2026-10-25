import copy
import unittest
from unittest.mock import patch

from test_validate_foundation_inputs import run
from test_verify_foundation_plan import module as plans
from test_verify_gala_bootstrap import module as bootstrap


TARGETS = plans.ALIGNMENT_SLUGS


def trial_changes(phase):
    changes = []
    for slug in TARGETS:
        instance, volume = plans.TEMPORARY_IDENTITIES[slug]
        before = {
            'id': instance, 'primary_network_interface_id': 'eni-0123456789abcdef0',
            'disable_api_termination': True,
            'tags': {'Project': 'tibillet-gala-paris', 'Gala': slug, 'ManagedBy': 'terraform'},
            'root_block_device': [{'volume_id': volume, 'volume_size': 40, 'delete_on_termination': False}],
        }
        after = copy.deepcopy(before)
        after['disable_api_termination'] = False
        after['root_block_device'][0]['delete_on_termination'] = True
        item = {'address': f'module.gala["{slug}"].aws_instance.retirable[0]'}
        if phase == 'prepare':
            item['previous_address'] = f'module.gala["{slug}"].aws_instance.runtime[0]'
            item['change'] = {'actions': ['update'], 'before': before, 'after': after, 'after_unknown': {}}
        else:
            item['change'] = {'actions': ['delete'], 'before': after, 'after': None, 'after_unknown': {}}
        changes.append(item)
    return {'resource_changes': changes}


class AlignmentRetirementTests(unittest.TestCase):
    def test_two_phase_catalog_preserves_aix_smoke_and_trial_keys(self):
        settings = {'platform': 'v1', 'domain': 'galas-am-aix.rezal.fr', 'instance_type': 't3.medium',
                    'root_volume_size_gib': 40, 'ssh_emergency_cidrs': [], 'associate_public_ip_address': True,
                    'create_instance': True, 'protect_from_destruction': True}
        catalog = {'version': 1, 'galas': {s: dict(settings) for s in (*TARGETS, 'gala-am-aix', 'gala-smoke')}}
        rejected, _, _ = run(catalog, GALA_NAME='Retire Gala Alignment')
        self.assertNotEqual(rejected.returncode, 0)
        prepared, _, proposal = run(catalog, GALA_NAME='Prepare Gala Alignment Retirement')
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertEqual(set(proposal['galas']), set(catalog['galas']))
        for s in TARGETS:
            self.assertTrue(proposal['galas'][s]['create_instance'])
            self.assertFalse(proposal['galas'][s]['protect_from_destruction'])
        rejected, _, _ = run(proposal)
        self.assertNotEqual(rejected.returncode, 0)
        retired, _, final = run(proposal, GALA_NAME='Retire Gala Alignment')
        self.assertEqual(retired.returncode, 0, retired.stderr)
        for s in TARGETS:
            self.assertFalse(final['galas'][s]['create_instance'])
        for s in ['gala-am-aix', 'gala-smoke']:
            self.assertEqual(final['galas'][s], catalog['galas'][s])

    def test_plan_requires_both_exact_trials_and_refuses_other_deletions(self):
        for phase in ['prepare', 'retire']:
            plan = trial_changes(phase)
            self.assertEqual(len(plans.verify_verification_retirement_plan(plan, phase, targets=TARGETS)), 2)
            for bad in [
                {'resource_changes': plan['resource_changes'][:1]},
                {'resource_changes': plan['resource_changes'] + [{
                    'address': 'module.gala["gala-am-aix"].aws_instance.runtime[0]',
                    'change': {'actions': ['delete'], 'before': {}, 'after': None}}]},
                {'resource_changes': plan['resource_changes'] + [{
                    'address': f'aws_cloudwatch_log_group.production_deploy["{TARGETS[0]}"]',
                    'change': {'actions': ['delete'], 'before': {}, 'after': None}}]},
            ]:
                with self.assertRaises(ValueError):
                    plans.verify_verification_retirement_plan(bad, phase, targets=TARGETS)
            for key in ['id', 'volume_id']:
                bad = copy.deepcopy(plan)
                before = bad['resource_changes'][0]['change']['before']
                if key == 'id': before[key] = 'i-00000000000000000'
                else: before['root_block_device'][0][key] = 'vol-00000000000000000'
                with self.assertRaises(ValueError):
                    plans.verify_verification_retirement_plan(bad, phase, targets=TARGETS)

    def test_bootstrap_allows_stopped_trials_only_with_completed_owned_snapshots(self):
        def responder(*args):
            if args[:2] == ('ssm', 'get-parameter'):
                return {'Parameter': {'Value': 'gala-smoke'}}
            if args[:2] == ('ec2', 'describe-snapshots'):
                identity = next(v for v in bootstrap.ALIGNMENT_IDENTITIES.values() if v[2] == args[3])
                return {'Snapshots': [{'State': 'completed', 'OwnerId': bootstrap.ACCOUNT,
                                       'VolumeId': identity[1], 'Encrypted': True}]}
            if args[:2] == ('ec2', 'describe-instances'):
                slug, identity = next((k, v) for k, v in bootstrap.ALIGNMENT_IDENTITIES.items() if v[0] == args[3])
                return {'Reservations': [{'Instances': [{'State': {'Name': 'stopped'},
                    'Tags': [{'Key': k, 'Value': v} for k, v in {'Project': 'tibillet-gala-paris', 'Gala': slug, 'ManagedBy': 'terraform'}.items()],
                    'BlockDeviceMappings': [{'Ebs': {'VolumeId': identity[1], 'DeleteOnTermination': True}}]}]}]}
            if args[:2] == ('ec2', 'describe-instance-attribute'):
                return {'DisableApiTermination': {'Value': False}}
            raise AssertionError(args)

        plan = trial_changes('prepare')
        with patch.object(bootstrap, 'aws', side_effect=responder):
            bootstrap.verify_validation_retirement(plan, 'prepare', 'tibillet-gala-paris', targets=TARGETS)
        for mutation in [lambda x: x.update(State='pending'), lambda x: x.update(Encrypted=False),
                         lambda x: x.update(OwnerId='000000000000'), lambda x: x.update(VolumeId='vol-00000000000000000')]:
            def bad_responder(*args):
                result = responder(*args)
                if args[:2] == ('ec2', 'describe-snapshots'): mutation(result['Snapshots'][0])
                return result
            with patch.object(bootstrap, 'aws', side_effect=bad_responder), self.assertRaises(RuntimeError):
                bootstrap.verify_validation_retirement(plan, 'prepare', 'tibillet-gala-paris', targets=TARGETS)

    def test_active_trial_is_never_retired(self):
        with patch.object(bootstrap, 'aws', return_value={'Parameter': {'Value': TARGETS[0]}}), self.assertRaises(RuntimeError):
            bootstrap.verify_validation_retirement(trial_changes('retire'), 'retire', 'tibillet-gala-paris', targets=TARGETS)

    def test_existing_delivery_policy_refresh_cannot_change_role_or_permissions(self):
        plan = trial_changes('retire')
        before = {'id': 'existing', 'name': 'existing', 'role': 'same-role', 'policy': '{}'}
        refresh = {'address': 'aws_iam_role_policy.production_build["gala-images-csv-2026-10-08"]',
                   'change': {'actions': ['update'], 'before': before,
                              'after': {**before, 'policy': None}, 'after_unknown': {'policy': True}}}
        plan['resource_changes'].append(refresh)
        self.assertEqual(len(plans.verify_verification_retirement_plan(plan, 'retire', targets=TARGETS)), 3)
        for mutation in [lambda c: c['after'].update(role='different-role'),
                         lambda c: c['after'].update(policy='{"Statement": []}'),
                         lambda c: c.update(after_unknown={'policy': True, 'role': True})]:
            bad = copy.deepcopy(plan)
            mutation(bad['resource_changes'][-1]['change'])
            with self.assertRaises(ValueError):
                plans.verify_verification_retirement_plan(bad, 'retire', targets=TARGETS)
