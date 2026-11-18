"""Move only existing Smoke hostnames, preserving pairings and balances."""
import argparse
import inspect
import json
import subprocess
from urllib.parse import urlsplit, urlunsplit

OLD = 'galas-am-aix.rezal.fr'
NEW = 'gala-test.rezal.fr'


def move_host(value, old, new):
    if value in (None, ''):
        return value
    if value in (old, new):
        return new
    url = urlsplit(value)
    if (url.scheme != 'https' or url.netloc not in {old, new}
            or url.path not in {'', '/'} or url.query or url.fragment):
        raise ValueError('Existing test pairing has an unexpected domain')
    return urlunsplit(('https', new, url.path, '', ''))


COMMON = '''import json, os, socket, ipaddress
from urllib.parse import urlsplit, urlunsplit
from django.db import transaction
''' + inspect.getsource(move_host) + '''
def private_ip(domain):
    value = socket.gethostbyname(domain)
    assert ipaddress.ip_address(value).is_private, 'peer must resolve to the local Docker gateway'
    return value

def patch_fields(model, row, values, apply):
    changed = {key: value for key, value in values.items() if getattr(row, key) != value}
    if changed and apply:
        before = {key: getattr(row, key) for key in changed}
        assert model.objects.filter(pk=row.pk, **before).update(**changed) == 1, 'pairing changed concurrently'
        if hasattr(model, 'clear_cache'):
            model.clear_cache()
    return len(changed)
'''


def lespass_code(apply):
    return COMMON + '''
from Customers.models import Client, Domain
from root_billet.models import RootConfiguration
from BaseBillet.models import Configuration, Event
from fedow_connect.models import FedowConfig
from django_tenants.utils import tenant_context
old, new, apply = %r
assert os.environ['DOMAIN'] == new and os.environ.get('GALA_LOCAL_FEDOW') == '1'
provider = os.environ.get('PAYMENT_PROVIDER', 'stripe')
assert os.environ.get('CAWL_TEST' if provider == 'cawl' else 'STRIPE_TEST') == '1'
def migrate():
    with transaction.atomic():
        roots = list(Domain.objects.select_for_update().filter(domain__in=[old, new]))
        if not roots:
            assert not Domain.objects.exists(), 'existing domains do not match the approved migration'
            return {'fresh': True, 'changes': 0}
        assert len(roots) == 1, 'old and new apex coexist; manual review required'
        gala = Client.objects.get(schema_name=os.environ['SUB'], categorie=Client.SALLE_SPECTACLE)
        assert roots[0].tenant_id == gala.pk, 'apex is not the paired Gala tenant'
        owners = {'public', os.environ['SUB'], os.environ['META']}
        labels = {'', 'www.', 'm.', os.environ['SUB']+'.', os.environ['META']+'.'}
        planned = []
        for label in labels:
            rows = list(Domain.objects.select_for_update().select_related('tenant').filter(domain__in=[label+old, label+new]))
            assert len(rows) <= 1, 'old and new domain coexist; manual review required'
            for row in rows:
                assert row.tenant.schema_name in owners, 'domain belongs to an unrelated tenant'
                planned.append((row, label+new))
        root = RootConfiguration.objects.select_for_update().get(pk=1)
        changes = patch_fields(RootConfiguration, root, {
            'fedow_domain': move_host(root.fedow_domain, 'fedow.'+old, 'fedow.'+new),
            'fedow_ip': private_ip('fedow.'+new)}, apply)
        with tenant_context(gala):
            paired = FedowConfig.objects.get(pk=1)
            assert paired.fedow_place_uuid and paired.fedow_place_wallet_uuid
            identity = {'place_uuid': str(paired.fedow_place_uuid), 'wallet_uuid': str(paired.fedow_place_wallet_uuid), 'tenant_schema': gala.schema_name}
            config = Configuration.objects.select_for_update().get(pk=1)
            changes += patch_fields(Configuration, config,
                {'server_cashless': move_host(config.server_cashless, 'cashless.'+old, 'cashless.'+new)}, apply)
            for event in Event.objects.select_for_update().filter(is_external=False).exclude(full_url__isnull=True).exclude(full_url=''):
                url = urlsplit(event.full_url)
                allowed_hosts = {old, new, gala.schema_name+'.'+old, gala.schema_name+'.'+new}
                assert url.scheme == 'https' and url.netloc in allowed_hosts and url.path.startswith('/event/') and not url.query and not url.fragment, 'unexpected internal event URL'
                target = urlunsplit(('https', new, url.path, '', ''))
                if event.full_url != target:
                    changes += 1
                    if apply:
                        assert Event.objects.filter(pk=event.pk, full_url=event.full_url).update(full_url=target) == 1
        for row, target in planned:
            if row.domain != target:
                changes += 1
                if apply:
                    assert Domain.objects.filter(pk=row.pk, domain=row.domain).update(domain=target) == 1
        return {'fresh': False, 'changes': changes, **identity}
print(json.dumps(migrate()))
''' % ((OLD, NEW, apply),)


def fedow_code(identity, apply):
    return COMMON + '''
from fedow_core.models import Configuration, Place
old, new, identity, apply = %r
assert os.environ['DOMAIN'] == 'fedow.'+new
assert os.environ.get('CAWL_TEST' if os.environ.get('PAYMENT_PROVIDER') == 'cawl' else 'STRIPE_TEST') == '1'
with transaction.atomic():
    config = Configuration.objects.select_for_update().get(pk=1)
    changes = patch_fields(Configuration, config, {'domain': move_host(config.domain, 'fedow.'+old, 'fedow.'+new)}, apply)
    place = Place.objects.select_for_update().get(uuid=identity['place_uuid'], wallet_id=identity['wallet_uuid'])
    assert place.lespass_domain in {old, new, identity['tenant_schema']+'.'+old, identity['tenant_schema']+'.'+new}
    changes += patch_fields(Place, place, {'lespass_domain': new,
        'cashless_server_url': move_host(place.cashless_server_url, 'cashless.'+old, 'cashless.'+new),
        'cashless_server_ip': private_ip('cashless.'+new)}, apply)
print(json.dumps({'changes': changes}))
''' % ((OLD, NEW, identity, apply),)


def laboutik_code(apply):
    return COMMON + '''
from APIcashless.models import Configuration
old, new, apply = %r
assert os.environ['DOMAIN'] == 'cashless.'+new
with transaction.atomic():
    config = Configuration.objects.select_for_update().get(pk=1)
    changes = patch_fields(Configuration, config, {
        'billetterie_url': move_host(config.billetterie_url, old, new),
        'fedow_domain': move_host(config.fedow_domain, 'fedow.'+old, 'fedow.'+new),
        'domaine_cashless': move_host(config.domaine_cashless, 'cashless.'+old, 'cashless.'+new)}, apply)
print(json.dumps({'changes': changes}))
''' % ((OLD, NEW, apply),)


def shell(service, code):
    cwd, poetry = ('/home/fedow/Fedow', 'poetry') if service == 'fedow' else ('/DjangoFiles', '/home/tibillet/.local/bin/poetry')
    result = subprocess.run(['docker', 'exec', '-i', '-w', cwd, service+'_django',
                             poetry, 'run', 'python', 'manage.py', 'shell'],
                            input=code, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Test domain migration refused in '+service+'; no secrets logged')
    return json.loads(result.stdout.strip().splitlines()[-1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gala', choices=['gala-smoke', 'gala-smoke-cawl'], required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    # Read and validate all three before writing. Retries permit a partial
    # completed migration, but never an unexpected domain or different peer.
    identity = shell('lespass', lespass_code(False))
    if identity['fresh']:
        print('Fresh test databases; native installation will create the approved domains')
        return
    shell('fedow', fedow_code(identity, False))
    shell('laboutik', laboutik_code(False))
    if not args.check:
        shell('lespass', lespass_code(True))
        shell('fedow', fedow_code(identity, True))
        shell('laboutik', laboutik_code(True))
    print('Test domain pairing '+('checked' if args.check else 'reconciled')+' for '+args.gala)


if __name__ == '__main__':
    main()
