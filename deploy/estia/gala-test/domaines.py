"""A fournir a manage.py shell. Plan par defaut ; aucune ecriture implicite.

ESTIA_DOMAIN_MODE=apply : bascule les deux domaines principaux.
ESTIA_DOMAIN_MODE=rollback : restaure les principaux observes le 02/11/2026.
Ne supprime aucun domaine, tenant, carte, compte ou transaction.
"""
import json
import os

from django.conf import settings
from django.db import transaction
from django_tenants.utils import schema_context
from Customers.models import Client, Domain

MODE = os.environ.get('ESTIA_DOMAIN_MODE', 'plan')
if MODE not in ('plan', 'apply', 'rollback'):
    raise RuntimeError('Mode attendu : plan, apply ou rollback')

TARGETS = (
    ('public', 'tibillet.localhost', 'gala-test.rezal.fr'),
    ('lespass', 'lespass.tibillet.localhost', 'cashless.gala-test.rezal.fr'),
)

with schema_context('public'), transaction.atomic():
    tenants = {}
    before = {}
    for schema, old, public in TARGETS:
        clients = Client.objects.all()
        domains = Domain.objects.all()
        if MODE != 'plan':
            clients = clients.select_for_update()
            domains = domains.select_for_update()
        tenant = clients.get(schema_name=schema)
        tenants[schema] = tenant
        rows = list(domains.filter(tenant=tenant))
        before[schema] = [
            {'domain': row.domain, 'is_primary': row.is_primary}
            for row in sorted(rows, key=lambda row: row.domain)
        ]
        current = [row.domain for row in rows if row.is_primary]
        if len(current) != 1 or current[0] not in (old, public):
            raise RuntimeError('Domaine principal inattendu pour ' + schema)
        if not any(row.domain == old for row in rows):
            raise RuntimeError('Ancien domaine absent pour ' + schema)
        conflict = Domain.objects.filter(domain=public).exclude(tenant=tenant).exists()
        if conflict:
            raise RuntimeError('Le domaine public appartient deja a un autre tenant : ' + public)

    print(json.dumps({'mode': MODE, 'avant': before, 'cibles': TARGETS}, indent=2))
    if MODE == 'apply':
        if 'gala-test.rezal.fr' not in settings.ALLOWED_HOSTS:
            raise RuntimeError('Les reglages publics de la VM ne sont pas encore charges')
        for schema, old, public in TARGETS:
            domain, _ = Domain.objects.get_or_create(
                domain=public, defaults={'tenant': tenants[schema], 'is_primary': False})
            domain.is_primary = True
            domain.save()  # DomainMixin demote les autres domaines de CE tenant.
        print('Domaines publics principaux ; anciens noms conserves comme alias en base.')
    elif MODE == 'rollback':
        for schema, old, public in TARGETS:
            domain = Domain.objects.get(domain=old, tenant=tenants[schema])
            domain.is_primary = True
            domain.save()
        print('Anciens domaines principaux retablis ; aucune suppression.')
    else:
        print('PLAN UNIQUEMENT : aucune ecriture en base.')
