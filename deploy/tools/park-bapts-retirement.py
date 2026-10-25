#!/usr/bin/env python3
"""Park the Paris public address before retiring the exact approved test Gala."""
import argparse
import json
import socket
import subprocess

ACCOUNT = '318629836660'
REGION = 'eu-west-3'
INSTANCE = 'i-0b1c966b50fd97f80'
VOLUME = 'vol-0d7ded144bdc952e8'
SNAPSHOT = 'snap-02ac5a5b7fb219952'
ALLOCATION = 'eipalloc-0a985f5daf0f7d969'
PARAMETER = '/tibillet-gala-paris/active-gala'
SLUG = 'baldubapts2026'


def aws(*args):
    result = subprocess.run(['aws', *args, '--region', REGION, '--output', 'json'],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def inspect():
    if aws('sts', 'get-caller-identity').get('Account') != ACCOUNT:
        raise ValueError('wrong AWS account')
    found = aws('ec2', 'describe-instances', '--instance-ids', INSTANCE)
    hosts = [i for r in found['Reservations'] for i in r['Instances']]
    if len(hosts) != 1 or hosts[0]['State']['Name'] != 'stopped':
        raise ValueError('exact Bapts EC2 must be stopped')
    tags = {v['Key']: v['Value'] for v in hosts[0].get('Tags', [])}
    if any(tags.get(k) != v for k, v in {'Project': 'tibillet-gala-paris', 'Gala': SLUG, 'ManagedBy': 'terraform'}.items()):
        raise ValueError('Bapts identity changed')
    if [v['Ebs']['VolumeId'] for v in hosts[0]['BlockDeviceMappings']] != [VOLUME]:
        raise ValueError('Bapts root volume changed')
    snapshots = aws('ec2', 'describe-snapshots', '--snapshot-ids', SNAPSHOT)['Snapshots']
    if len(snapshots) != 1 or any(snapshots[0].get(k) != v for k, v in {
        'State': 'completed', 'OwnerId': ACCOUNT, 'VolumeId': VOLUME, 'Encrypted': True}.items()):
        raise ValueError('completed encrypted Bapts archive is required')
    addresses = aws('ec2', 'describe-addresses', '--allocation-ids', ALLOCATION)['Addresses']
    if len(addresses) != 1 or addresses[0].get('InstanceId') not in {None, INSTANCE}:
        raise ValueError('Paris address is attached to another Gala')
    eip = addresses[0]
    marker = aws('ssm', 'get-parameter', '--name', PARAMETER)['Parameter']['Value']
    if marker not in {SLUG, 'none'} or (marker == 'none' and eip.get('InstanceId')):
        raise ValueError('active Gala changed')
    for domain in ('galas-am-aix.rezal.fr', 'fedow.galas-am-aix.rezal.fr', 'cashless.galas-am-aix.rezal.fr'):
        ips = {entry[4][0] for entry in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)}
        if eip['PublicIp'] in ips:
            raise ValueError('public DNS still routes traffic to the retiring Gala')
    return eip, marker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--check-retirement', action='store_true')
    args = parser.parse_args()
    if args.apply and args.check_retirement:
        raise ValueError('choose apply or read-only check')
    eip, marker = inspect()
    if args.check_retirement:
        if eip.get('AssociationId') or marker != 'none':
            raise ValueError('park Paris address before retirement')
        print('Bapts retirement prerequisites verified')
        return
    print(json.dumps({'instance': INSTANCE, 'volume': VOLUME, 'snapshot': SNAPSHOT,
                      'preserve_allocation': ALLOCATION, 'previous_active_gala': marker,
                      'next_active_gala': 'none', 'public_dns_change': False}, indent=2))
    if args.apply:
        # inspect() refreshes the exact stopped host, archive and routing before
        # this operation; an interrupted park can safely finish on retry.
        if eip.get('AssociationId'):
            aws('ec2', 'disassociate-address', '--association-id', eip['AssociationId'])
        if marker != 'none':
            aws('ssm', 'put-parameter', '--name', PARAMETER, '--type', 'String', '--value', 'none', '--overwrite')
        eip, marker = inspect()
        if eip.get('AssociationId') or marker != 'none':
            raise ValueError('Paris address parking did not complete')
        print('Paris address parked; public DNS and Stockholm remain unchanged')


if __name__ == '__main__':
    main()
