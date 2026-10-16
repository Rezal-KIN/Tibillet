from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Soumettre et rapprocher les remboursements CAWL du solde cashless"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if settings.PAYMENT_PROVIDER != "cawl":
            raise CommandError("Cette commande nécessite PAYMENT_PROVIDER=cawl.")
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("--limit doit être compris entre 1 et 1000.")
        from cawl_fedow.refunds import reconcile_pending_refunds

        count = reconcile_pending_refunds(options["limit"])
        self.stdout.write(f"{count} remboursement(s) de solde CAWL vérifié(s).")
