"""Assign the shared public hostname to this Gala's Lespass tenant.

The upstream installer gives the apex to the generic public tenant. Gala
deployments use the apex for their event/QR site instead. Run this command
after ``install`` on *every* release so fresh and existing Galas converge.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from Customers.models import Client, Domain


class Command(BaseCommand):
    help = 'Idempotently route the shared Lespass apex to the Gala tenant'

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true', help='Verify without changing domains')

    def handle(self, *args, **options):
        if os.environ.get('GALA_APEX_TENANT') != '1':
            raise CommandError('GALA_APEX_TENANT=1 is required')
        domain = os.environ.get('DOMAIN', '').strip().lower()
        subdomain = slugify(os.environ.get('SUB', ''))
        if not domain or not subdomain or '.' in subdomain or '/' in domain:
            raise CommandError('DOMAIN and SUB must identify one Gala')

        with transaction.atomic():
            try:
                public = Client.objects.get(schema_name='public', categorie=Client.ROOT)
                gala = Client.objects.get(schema_name=subdomain, categorie=Client.SALLE_SPECTACLE)
                apex = Domain.objects.select_for_update().get(domain=domain)
                www = Domain.objects.select_for_update().get(domain=f'www.{domain}', tenant=public)
                first = Domain.objects.select_for_update().get(
                    domain=f'{subdomain}.{domain}', tenant=gala,
                )
            except (Client.DoesNotExist, Domain.DoesNotExist) as error:
                raise CommandError('Gala tenant or expected domains are missing') from error

            if apex.tenant_id not in (public.pk, gala.pk):
                raise CommandError('apex is owned by an unexpected tenant')

            if options.get('check'):
                if not (apex.tenant_id == gala.pk and apex.is_primary
                        and www.is_primary and not first.is_primary):
                    raise CommandError('Gala apex does not route to the Gala tenant')
                self.stdout.write(self.style.SUCCESS(f'Gala apex verified: {domain} -> {subdomain}'))
                return

            # Preserve a primary address for the internal public tenant, while
            # making QR redirects and magic-link emails resolve to the apex.
            if not www.is_primary:
                www.is_primary = True
                www.save(update_fields=['is_primary'])
            if first.is_primary:
                first.is_primary = False
                first.save(update_fields=['is_primary'])
            if apex.tenant_id != gala.pk or not apex.is_primary:
                apex.tenant = gala
                apex.is_primary = True
                apex.save(update_fields=['tenant', 'is_primary'])

        self.stdout.write(self.style.SUCCESS(f'Gala apex reconciled: {domain} -> {subdomain}'))
