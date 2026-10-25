import os
from django.apps import AppConfig


class CawlLaboutikConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cawl_laboutik'

    def ready(self):
        if os.environ.get('PAYMENT_PROVIDER', 'stripe') == 'cawl':
            from APIcashless.models import MoyenPaiement
            if not any(code == 'CW' for code, _ in MoyenPaiement.CATEGORIES):
                MoyenPaiement.CATEGORIES.append(('CW', 'CAWL (en ligne)'))
            # FR : Le contrat de vente natif doit accepter le même code que Lespass.
            # EN: Preserve the native sale handler, with an explicit provider code.
            from APIcashless.validator import SaleFromLespassValidator
            SaleFromLespassValidator._declared_fields['payment_method'].choices = MoyenPaiement.CATEGORIES
