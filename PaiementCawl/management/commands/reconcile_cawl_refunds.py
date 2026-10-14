from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context


class Command(BaseCommand):
    help = 'Rapprocher les remboursements CAWL non confirmés pour une organisation'

    def add_arguments(self, parser):
        parser.add_argument('--schema', required=True)

    def handle(self, *args, **options):
        from Customers.models import Client
        from PaiementCawl.models import CawlRefund
        from PaiementCawl.refunds import reconcile_refund
        tenant = Client.objects.get(schema_name=options['schema'])
        with tenant_context(tenant):
            count = 0
            refunds = CawlRefund.objects.filter(accounted=False, provider_refund_id__isnull=False).select_related('payment')
            for refund in refunds:
                reconcile_refund(refund)
                count += 1
        self.stdout.write(f'{count} remboursement(s) CAWL vérifié(s).')
