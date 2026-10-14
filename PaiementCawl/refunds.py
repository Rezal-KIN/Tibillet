from decimal import Decimal
from uuid import UUID, uuid5

from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext as _

from payment_providers.cawl import CawlError
from PaiementCawl.models import CawlPayment, CawlRefund
from PaiementCawl.services import check_account, gateway


def finish_refund(refund, response):
    from BaseBillet.models import LigneArticle, Paiement_stripe, SaleOrigin

    if response.get("id") != refund.provider_refund_id:
        raise CawlError("Identifiant de remboursement CAWL incohérent.")
    money = response.get("refundOutput", {}).get("amountOfMoney", {})
    if money.get("amount") != refund.amount or money.get("currencyCode") != "EUR":
        raise CawlError("Montant du remboursement CAWL incohérent.")
    with transaction.atomic():
        # FR : Même ordre de verrous que la confirmation de paiement.
        # EN: Use the same lock order as payment confirmation.
        Paiement_stripe.objects.select_for_update().get(pk=refund.payment_id)
        payment = CawlPayment.objects.select_for_update().get(pk=refund.payment_id)
        locked = CawlRefund.objects.select_for_update().get(pk=refund.pk)
        locked.status = response["status"]
        locked.save(update_fields=["status"])
        if locked.accounted or locked.status != "REFUNDED":
            return
        for allocation in locked.allocations:
            line = LigneArticle.objects.get(pk=allocation["line"])
            metadata = dict(line.metadata or {})
            metadata["original_lignearticle_uuid"] = str(line.pk)
            metadata["cawl_refund_operation"] = str(locked.pk)
            negative = LigneArticle.objects.create(
                pricesold=line.pricesold, qty=-Decimal(allocation["qty"]),
                amount=line.amount, vat=line.vat, paiement_stripe=line.paiement_stripe,
                payment_method=line.payment_method, asset=line.asset, wallet=line.wallet,
                reservation=line.reservation, status=LigneArticle.CREATED,
                metadata=metadata, sale_origin=SaleOrigin.LESPASS,
            )
            negative.status = LigneArticle.REFUNDED
            negative.save(update_fields=["status"])
        locked.accounted = True
        locked.save(update_fields=["accounted"])
        completed = payment.refunds.filter(accounted=True).aggregate(total=Sum("amount"))["total"] or 0
        if completed == payment.amount:
            payment.payment.status = Paiement_stripe.REFUNDED
            payment.payment.save(update_fields=["status"])


def reconcile_refund(refund):
    client = gateway()
    check_account(refund.payment, client)
    for response in client.get_refunds(refund.payment.provider_payment_id):
        if response.get("id") == refund.provider_refund_id:
            finish_refund(refund, response)
            return


def cancel_reservation(reservation, ticket=None):
    from BaseBillet.models import LigneArticle, Paiement_stripe, Reservation, Ticket

    if ticket and ticket.reservation_id != reservation.pk:
        raise CawlError("Le billet n'appartient pas à cette réservation.")
    if reservation.tickets.filter(status=Ticket.SCANNED).exists() and not ticket:
        raise CawlError("Une réservation avec un billet scanné ne peut pas être remboursée.")
    if ticket and ticket.status == Ticket.SCANNED:
        raise CawlError("Un billet scanné ne peut pas être remboursé.")
    payments = reservation.paiements.filter(status__in=[Paiement_stripe.VALID, Paiement_stripe.PAID, Paiement_stripe.NOTSYNC])
    if payments.filter(cawl_payment__isnull=True).exists():
        raise CawlError("Un paiement Stripe historique doit être remboursé auprès de Stripe.")
    requested = []
    client = gateway()
    for payment in payments:
        with transaction.atomic():
            Paiement_stripe.objects.select_for_update().get(pk=payment.pk)
            record = CawlPayment.objects.select_for_update().get(payment=payment)
            check_account(record, client)
            if not record.provider_payment_id:
                raise CawlError("Ce paiement CAWL doit être rapproché avant son remboursement.")
            identity = str(ticket.pk) if ticket else "reservation-complete"
            operation_id = uuid5(UUID(str(payment.pk)), identity)
            refund = CawlRefund.objects.filter(pk=operation_id).first()
            if refund is None:
                previous = list(record.refunds.all())
                allocations = []
                total = Decimal("0")
                lines = payment.lignearticles.filter(status=LigneArticle.VALID, qty__gt=0)
                if ticket:
                    lines = lines.filter(pricesold_id=ticket.pricesold_id)
                for line in lines:
                    remaining = Decimal(str(line.qty))
                    for prior in previous:
                        if prior.status == "REJECTED":
                            continue
                        for allocation in prior.allocations:
                            if allocation["line"] == str(line.pk):
                                remaining -= Decimal(allocation["qty"])
                    quantity = min(Decimal("1"), remaining) if ticket else remaining
                    if quantity > 0:
                        allocations.append({"line": str(line.pk), "qty": str(quantity)})
                        total += quantity * line.amount
                        if ticket:
                            break
                if total <= 0:
                    continue
                # FR : Le plafond inclut les remboursements déjà demandés ou confirmés.
                # EN: The cap includes refunds already requested or confirmed.
                already = sum(prior.amount for prior in previous if prior.status != "REJECTED")
                if total != total.to_integral_value() or already + total > record.amount:
                    raise CawlError("Montant de remboursement invalide.")
                refund = CawlRefund.objects.create(
                    operation_id=operation_id, payment=record, amount=int(total), allocations=allocations,
                )
            requested.append(refund)
        if refund.status == "CREATED":
            response = client.refund(record.provider_payment_id, refund.amount, refund.pk)
            refund.provider_refund_id = response["id"]
            refund.save(update_fields=["provider_refund_id"])
            finish_refund(refund, response)
        refund.refresh_from_db()
        if refund.status == "REJECTED":
            raise CawlError("Le remboursement a été refusé par CAWL.")
    if not requested:
        raise CawlError("Aucune ligne disponible pour ce remboursement CAWL.")
    if ticket:
        ticket.status = Ticket.CANCELED
        ticket.save(update_fields=["status"])
    else:
        reservation.tickets.update(status=Ticket.CANCELED)
        reservation.status = Reservation.CANCELED
        reservation.save(update_fields=["status"])
    return _("Annulation enregistrée. Le remboursement est suivi auprès de CAWL.")
