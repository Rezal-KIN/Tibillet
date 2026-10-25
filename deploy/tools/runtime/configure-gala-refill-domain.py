#!/usr/bin/env python3
"""Keep the paired Fedow place on the Gala's canonical Lespass hostname.

The native installer creates the place before configure_gala_apex moves the
primary hostname. Stripe and Fedow webhooks subsequently use this stored
domain. Only deployment configuration changes; recharge handling stays native.
"""

import argparse
import json
import re
import subprocess


def django_shell(service, code):
    cwd = '/home/fedow/Fedow' if service == 'fedow' else '/DjangoFiles'
    poetry = 'poetry' if service == 'fedow' else '/home/tibillet/.local/bin/poetry'
    result = subprocess.run(
        ['docker', 'exec', '-i', '-w', cwd, service + '_django',
         poetry, 'run', 'python', 'manage.py', 'shell'],
        input=code, text=True, capture_output=True, timeout=60,
    )
    if result.returncode:
        raise RuntimeError('Gala refill domain configuration failed for ' + service)
    return json.loads(result.stdout.strip().splitlines()[-1])


def lespass_code(domain):
    return '''import json, os
from Customers.models import Client, Domain
from django_tenants.utils import tenant_context
from fedow_connect.models import FedowConfig
domain = %r
assert os.environ.get('GALA_APEX_TENANT') == '1'
assert os.environ['DOMAIN'] == domain
tenant = Domain.objects.get(domain=domain, is_primary=True).tenant
assert tenant.schema_name == os.environ['SUB'] and tenant.categorie == Client.SALLE_SPECTACLE
with tenant_context(tenant):
    config = FedowConfig.get_solo()
    assert config.fedow_place_uuid and config.fedow_place_wallet_uuid
    print(json.dumps({'place_uuid': str(config.fedow_place_uuid),
        'wallet_uuid': str(config.fedow_place_wallet_uuid),
        'legacy_domain': tenant.schema_name + '.' + domain}))
''' % domain


def fedow_code(identity, domain, check):
    return '''import json
from django.db import transaction
from fedow_core.models import Place
identity, domain, check = %r
with transaction.atomic():
    place = Place.objects.select_for_update().get(
        uuid=identity['place_uuid'], wallet_id=identity['wallet_uuid'])
    assert place.lespass_domain in {domain, identity['legacy_domain']}, 'unexpected Lespass domain'
    if check:
        assert place.lespass_domain == domain, 'Fedow refill return domain is not canonical'
    elif place.lespass_domain != domain:
        place.lespass_domain = domain
        place.save(update_fields=['lespass_domain'])
    print(json.dumps({'domain': place.lespass_domain, 'status': 'ready'}))
''' % ((identity, domain, check),)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--check', action='store_true', help='Verify without changing configuration')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', args.domain):
        parser.error('domain must be a lowercase hostname')
    identity = django_shell('lespass', lespass_code(args.domain))
    result = django_shell('fedow', fedow_code(identity, args.domain, args.check))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
