"""Keep the QR-card refill action visible on every deployed Gala.

Gala cashless refills use Fedow's shared Stripe account, not Lespass ticket
payouts. Lespass otherwise hides the action when no Connect payout account is
configured. Run after Fedow credentials have been reconciled on each release.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration
from Customers.models import Client


class Command(BaseCommand):
    help = 'Idempotently enable the Gala QR-card refill action'

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true', help='Verify without changing configuration')

    def handle(self, *args, **options):
        if os.environ.get('GALA_APEX_TENANT') != '1':
            raise CommandError('GALA_APEX_TENANT=1 is required')
        subdomain = slugify(os.environ.get('SUB', ''))
        if not subdomain or subdomain != os.environ.get('SUB'):
            raise CommandError('SUB must identify one Gala tenant')
        stripe_test = os.environ.get('STRIPE_TEST')
        if stripe_test not in {'0', '1'}:
            raise CommandError('STRIPE_TEST must be 0 or 1')
        mode = 'test' if stripe_test == '1' else 'live'
        key_name = 'STRIPE_KEY_TEST' if mode == 'test' else 'STRIPE_KEY'
        webhook_name = 'STRIPE_ENDPOINT_SECRET_TEST' if mode == 'test' else 'STRIPE_ENDPOINT_SECRET'
        if not (os.environ.get(key_name, '').startswith(f'sk_{mode}_')
                and os.environ.get(webhook_name, '').startswith('whsec_')):
            raise CommandError('Gala Stripe credentials are missing or invalid')

        try:
            gala = Client.objects.get(schema_name=subdomain, categorie=Client.SALLE_SPECTACLE)
        except Client.DoesNotExist as error:
            raise CommandError('Gala tenant is missing') from error

        with tenant_context(gala), transaction.atomic():
            config = Configuration.get_solo()
            if config.hide_refill_button:
                raise CommandError('Gala refill is explicitly hidden; refusing to override it')
            if options.get('check'):
                if not (config.force_show_refill_button and config.show_refill_button()):
                    raise CommandError('Gala QR-card refill is not visible')
                self.stdout.write(self.style.SUCCESS('Gala QR-card refill verified'))
                return
            if not config.force_show_refill_button:
                config.force_show_refill_button = True
                config.save(update_fields=['force_show_refill_button'])

        self.stdout.write(self.style.SUCCESS('Gala QR-card refill ready'))
