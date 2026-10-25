from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context


class Command(BaseCommand):
    help = "Relit chez CAWL l'état des remboursements d'un lieu (alerte si la banque en refuse un)."

    def add_arguments(self, parser):
        parser.add_argument('--schema', required=True)

    def handle(self, *args, **options):
        from Customers.models import Client
        from PaiementCawl.models import CawlRefund
        from PaiementCawl.services import rapprocher_le_remboursement

        tenant = Client.objects.get(schema_name=options['schema'])
        with tenant_context(tenant):
            nombre = 0
            remboursements = CawlRefund.objects.filter(
                provider_refund_id__isnull=False,
            ).exclude(status__in=["REFUNDED", "REJECTED"]).select_related('payment')
            for remboursement in remboursements:
                rapprocher_le_remboursement(remboursement)
                nombre += 1
        self.stdout.write(f'{nombre} remboursement(s) CAWL vérifié(s).')
