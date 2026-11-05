"""Suite CAWL sur une COPIE jetable de la base, jamais sur la base du site.
/ Run the CAWL suite against a disposable database copy, never the website database.
"""
import io
from contextlib import redirect_stdout
import os
import sys
from pathlib import Path

if not os.environ.get('POSTGRES_DB', '').startswith('ci_cawl_'):
    raise SystemExit('ARRÊT : une base ci_cawl_ dédiée aux tests est obligatoire.')

os.environ.update(TEST='1', DEBUG='1', DEMO='1', EMAIL_DELIVERY_MODE='capture', EMAIL_DELIVERY_GUARD='1')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from django.conf import settings

# Aucun cache ni worker partagé avec le site. / No shared cache or worker with the site.
settings.CACHES = {
    name: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
           'LOCATION': os.environ['POSTGRES_DB'], 'KEY_FUNCTION': 'django_tenants.cache.make_key'}
    for name in settings.CACHES
}
settings.SOLO_CACHE = None
settings.CELERY_BROKER_URL = 'memory://'
settings.CELERY_RESULT_BACKEND = 'cache+memory://'

import django
django.setup()
from django.core.management import call_command
from celery import current_app
current_app.conf.update(broker_url='memory://', result_backend='cache+memory://')

# La fixture native réutilise cette clé de la COPIE, sans lancer un autre processus.
# / Native fixtures reuse this key from the COPY without spawning another process.
call_command('migrate_schemas', verbosity=0)
output = io.StringIO()
with redirect_stdout(output):
    call_command('test_api_key', stdout=output)
os.environ['API_KEY'] = output.getvalue().strip().splitlines()[-1]

import pytest
raise SystemExit(pytest.main([
    '-q', '--tb=short', '--maxfail=5',
    'tests/pytest/test_laboutik_entree.py',
    'tests/pytest/test_cawl_ventes.py',
    'tests/pytest/test_cawl_passerelle.py',
    'tests/pytest/test_garde_aucun_amount_fois_qty.py',
    'tests/pytest/test_plan_comptable_unique.py',
    'tests/pytest/test_qr_parcours_securise.py',
    'tests/pytest/test_carte_perdue_cycle_complet.py',
    'tests/pytest/test_vues_carte_branchees_sur_service.py',
    'tests/pytest/test_carte_liee_chez_fedow_fed_en_caisse.py',
]))
