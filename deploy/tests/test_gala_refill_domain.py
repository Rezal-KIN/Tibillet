"""Exercise domain reconciliation against an isolated SQLite database."""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[1] / 'tools/runtime'
SCRIPT = RUNTIME / 'configure-gala-refill-domain.py'


class GalaRefillDomainTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('django'), 'requires Django for the ORM regression')
    def test_reconcile_paired_place_and_refuse_unexpected_configuration(self):
        probe = r'''
import contextlib, importlib.util, io, sys, types
from uuid import uuid4
from django.conf import settings
settings.configure(SECRET_KEY='isolated-test', INSTALLED_APPS=[],
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}})
import django
django.setup()
from django.db import connection, models
from django.db.models.signals import post_save
class Place(models.Model):
    uuid = models.UUIDField(primary_key=True)
    wallet_id = models.UUIDField()
    lespass_domain = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    class Meta:
        app_label = 'fedow_core'
with connection.schema_editor() as schema:
    schema.create_model(Place)
domain = 'galas-am-aix.rezal.fr'
legacy = 'festival.' + domain
place = Place.objects.create(uuid=uuid4(), wallet_id=uuid4(), lespass_domain=legacy, name='Festival')
peer = Place.objects.create(uuid=uuid4(), wallet_id=uuid4(), lespass_domain=legacy, name='Other')
identity = {'place_uuid': str(place.pk), 'wallet_uuid': str(place.wallet_id), 'legacy_domain': legacy}
sys.modules['fedow_core.models'] = types.SimpleNamespace(Place=Place)
spec = importlib.util.spec_from_file_location('refill_domain', sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
writes = []
def saved(sender, instance, update_fields, **kwargs):
    writes.append((instance.pk, update_fields))
post_save.connect(saved, sender=Place)
def run(check, target=identity):
    with contextlib.redirect_stdout(io.StringIO()):
        exec(mod.fedow_code(target, domain, check))
try:
    run(True)
except AssertionError:
    pass
else:
    raise AssertionError('stale return domain passed readiness')
assert writes == []
place.refresh_from_db()
assert place.lespass_domain == legacy
run(False)
run(False)
run(True)
assert writes == [(place.pk, frozenset({'lespass_domain'}))]
place.refresh_from_db(); peer.refresh_from_db()
assert place.lespass_domain == domain and place.name == 'Festival'
assert peer.lespass_domain == legacy
try:
    run(False, {**identity, 'wallet_uuid': str(uuid4())})
except Place.DoesNotExist:
    pass
else:
    raise AssertionError('mismatched pairing was accepted')
Place.objects.filter(pk=place.pk).update(lespass_domain='other.example.org')
for check in (False, True):
    try:
        run(check)
    except AssertionError:
        pass
    else:
        raise AssertionError('unrelated domain was overwritten or accepted')
place.refresh_from_db()
assert place.lespass_domain == 'other.example.org' and len(writes) == 1
'''
        result = subprocess.run([sys.executable, '-c', probe, str(SCRIPT)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_deployment_updates_domain_after_apex_and_healthcheck_verifies_it(self):
        release = (RUNTIME / 'deploy-release.sh').read_text()
        self.assertLess(release.index('manage.py configure_gala_apex'),
                        release.index('configure-gala-refill-domain.py'))
        self.assertLess(release.index('configure-gala-refill-domain.py'),
                        release.index('healthy=false'))
        health = (RUNTIME / 'healthcheck.sh').read_text()
        self.assertIn('configure-gala-refill-domain.py" --domain "$LESPASS_PUBLIC_DOMAIN" --check', health)


if __name__ == '__main__':
    unittest.main()
