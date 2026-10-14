import os
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    def handle(self, *args, **options):
        if os.environ.get('PAYMENT_PROVIDER', 'stripe') != 'cawl':
            self.stdout.write('CAWL non sélectionné ; configuration existante conservée.')
            return
        from APIcashless.models import MoyenPaiement
        method, created = MoyenPaiement.objects.get_or_create(categorie='CW', defaults={'name': 'CAWL (en ligne)'})
        if method.name != 'CAWL (en ligne)':
            raise CommandError('Le code de paiement CW est déjà utilisé par un autre moyen de paiement.')
        self.stdout.write('Moyen de paiement CAWL prêt pour les ventes Lespass.')
