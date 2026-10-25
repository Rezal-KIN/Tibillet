import os
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    def handle(self, *args, **options):
        if getattr(settings, 'PAYMENT_PROVIDER', 'stripe') != 'cawl':
            from fedow_core.management.commands.install import Command as NativeInstall
            return NativeInstall().handle(*args, **options)
        from cawl_fedow.services import gateway
        from fedow_core.models import Asset, Configuration, Federation, asset_creator, wallet_creator
        gateway()
        with transaction.atomic():
            if Configuration.objects.exists():
                self.stdout.write('Configuration Fedow existante conservée.')
                return
            wallet = wallet_creator(name='Primary Wallet', generate_rsa=True)
            Configuration.objects.create(name=os.environ['DOMAIN'], domain=os.environ['DOMAIN'], primary_wallet=wallet)
            asset_creator(name='Primary Asset', currency_code='FED', category=Asset.STRIPE_FED_FIAT, wallet_origin=wallet)
            Federation.objects.create(name='Fedow')
        self.stdout.write('Fedow CAWL installé ; validation du compte marchand à effectuer séparément.')
