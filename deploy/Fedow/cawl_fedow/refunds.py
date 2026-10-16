"""Refund original CAWL recharges without leaving their tokens spendable.

FR : Les appels bancaires sont hors transaction SQLite. Le journal natif réserve
le solde avant l'appel ; seul un refus bancaire définitif autorise sa restitution.
EN: Provider calls never hold the ledger lock. Uncertain outcomes stay reserved.
"""

import logging
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from fedow_core.models import Asset, Configuration, Token, Transaction, Wallet
from fedow_core.utils import get_request_ip
from payment_providers.cawl import CawlError
from cawl_fedow.models import Checkout, WalletRefund, WalletRefundRequest
from cawl_fedow.services import gateway

logger = logging.getLogger(__name__)
RELEASED = {"REJECTED", "CANCELLED"}
TERMINAL = RELEASED | {"REFUNDED"}
# CAWL guarantees idempotence for at least 24 h. Never re-submit beyond 23 h.
RETRY_WINDOW = timedelta(hours=23)
ATTEMPT_LEASE = timedelta(minutes=2)


def lock_wallet(wallet_id):
    # SQLite BEGIN DEFERRED needs a write BEFORE any balance read; PostgreSQL
    # additionally locks the wallet row. No provider request runs under this lock.
    Wallet.objects.filter(pk=wallet_id).update(name=F("name"))
    return Wallet.objects.select_for_update().get(pk=wallet_id)


def check_account(checkout, client):
    if (checkout.merchant_id != client.configuration.merchant_id
            or checkout.test_mode != client.configuration.test_mode):
        raise CawlError("Le compte ou l'environnement CAWL du remboursement a changé.")


def ledger_entry(batch, checkout, amount, action, operation_id):
    primary = Configuration.get_solo().primary_wallet
    if checkout.asset.wallet_origin_id != primary.pk or checkout.asset.category != Asset.STRIPE_FED_FIAT:
        raise CawlError("L'émetteur du solde à rembourser est incohérent.")
    entry = Transaction.objects.create(
        sender=primary if action == Transaction.CORRECTION else batch.wallet,
        receiver=batch.wallet if action == Transaction.CORRECTION else primary,
        asset=checkout.asset, amount=amount, action=action, ip=batch.ip,
        metadata={"payment_provider": "cawl", "cawl_wallet_refund": str(operation_id),
                  "cawl_refund_request": str(batch.pk), "cawl_checkout_uuid": str(checkout.pk),
                  "phase": "release" if action == Transaction.CORRECTION else "reserve"},
    )
    if not entry.verify_hash():
        raise CawlError("Le journal du remboursement est invalide.")
    return entry


def prepare_wallet_refund(request, request_id):
    """Reserve the full online balance atomically; browser supplies no amount."""
    request_id = UUID(str(request_id))
    client = gateway()
    with transaction.atomic():
        wallet = lock_wallet(request.wallet.pk)
        previous = WalletRefundRequest.objects.filter(pk=request_id).first()
        if previous:
            if previous.wallet_id != wallet.pk or previous.place_id != request.place.pk:
                raise CawlError("Cette demande de remboursement n'appartient pas à ce portefeuille.")
            return previous, False
        if WalletRefund.objects.filter(request__wallet=wallet).exclude(status__in=TERMINAL).exists():
            raise CawlError("Une demande de remboursement est déjà en cours pour ce portefeuille.")
        primary = Configuration.get_solo().primary_wallet
        token = Token.objects.select_for_update().filter(
            wallet=wallet, asset__wallet_origin=primary, asset__category=Asset.STRIPE_FED_FIAT,
        ).first()
        amount = token.value if token else 0
        remaining = amount
        allocations = []
        if remaining:
            checkouts = Checkout.objects.select_for_update().filter(
                wallet=wallet, place=request.place, asset=token.asset, refill__isnull=False,
                provider_payment_id__isnull=False, merchant_id=client.configuration.merchant_id,
                test_mode=client.configuration.test_mode,
            ).order_by("-created_at", "uuid")
            for checkout in checkouts:
                used = checkout.refunds.exclude(status__in=RELEASED).aggregate(total=Sum("amount"))["total"] or 0
                available = checkout.amount - used
                if available < 0:
                    raise CawlError("Les remboursements de cette recharge doivent être rapprochés.")
                value = min(remaining, available)
                if value:
                    allocations.append((checkout, value))
                    remaining -= value
                if not remaining:
                    break
        if remaining:
            raise CawlError("Ce solde ne peut pas être remboursé intégralement en ligne par ce collectif. Contactez-le.")
        batch = WalletRefundRequest.objects.create(
            uuid=request_id, wallet=wallet, place=request.place, amount=amount,
            ip=get_request_ip(request) or "0.0.0.0",
        )
        for checkout, value in allocations:
            refund = WalletRefund(request=batch, checkout=checkout, amount=value)
            refund.debit = ledger_entry(batch, checkout, value, Transaction.REFUND, refund.pk)
            refund.save(force_insert=True)
        return batch, True


def refund_summary(batch):
    refunds = list(batch.refunds.all())
    refunded = sum(item.amount for item in refunds if item.status == "REFUNDED")
    released = sum(item.amount for item in refunds if item.release_id)
    pending = batch.amount - refunded - released
    status = "PENDING" if pending else ("REFUNDED" if refunded else "REJECTED")
    if not batch.amount:
        status = "EMPTY"
    elif any(item.status == "REVIEW" for item in refunds):
        status = "REVIEW"
    elif not pending and released and refunded:
        status = "PARTIAL"
    return {"request_id": str(batch.pk), "amount": batch.amount, "refunded": refunded,
            "released": released, "pending": pending, "status": status}


def reference(response):
    return response.get("refundOutput", {}).get("operationReferences", {}).get("merchantReference")


def finish_wallet_refund(refund, response):
    provider_id = response.get("id")
    money = response.get("refundOutput", {}).get("amountOfMoney", {})
    if (not isinstance(provider_id, str) or not provider_id
            or type(money.get("amount")) is not int or money["amount"] != refund.amount
            or money.get("currencyCode") != "EUR"
            or (reference(response) is not None and reference(response) != refund.pk.hex)):
        raise CawlError("La réponse de remboursement CAWL ne correspond pas à la demande.")
    status = response.get("status")
    if not isinstance(status, str) or not status or len(status) > 64:
        raise CawlError("Le statut du remboursement CAWL est invalide.")
    with transaction.atomic():
        lock_wallet(refund.request.wallet_id)
        locked = WalletRefund.objects.select_for_update().select_related(
            "request__wallet", "checkout__asset").get(pk=refund.pk)
        if locked.provider_refund_id and locked.provider_refund_id != provider_id:
            raise CawlError("L'identifiant bancaire du remboursement a changé.")
        if locked.status in TERMINAL:
            # Ignore stale in-progress callbacks, never reverse a final outcome.
            if status in TERMINAL and status != locked.status:
                raise CawlError("Deux résultats définitifs de remboursement se contredisent.")
            return
        locked.provider_refund_id = provider_id
        locked.status = status
        locked.error_code = ""
        if status in RELEASED and not locked.release_id:
            locked.release = ledger_entry(locked.request, locked.checkout, locked.amount,
                                          Transaction.CORRECTION, locked.pk)
        locked.save(update_fields=["provider_refund_id", "status", "error_code", "release", "updated_at"])


def note_error(refund, code, review=False):
    changes = {"error_code": code, "updated_at": timezone.now()}
    if review:
        changes["status"] = "REVIEW"
    WalletRefund.objects.filter(pk=refund.pk).exclude(status__in=TERMINAL).update(**changes)
    logger.warning("Remboursement CAWL %s : %s", refund.pk, code)


def reconcile_wallet_refund(refund, submit=True):
    """Read authoritative state first; safely retry the SAME operation if needed."""
    if refund.status in TERMINAL:
        return
    client = gateway()
    check_account(refund.checkout, client)
    responses = client.get_refunds(refund.checkout.provider_payment_id)
    matches = [response for response in responses if (
        response.get("id") == refund.provider_refund_id if refund.provider_refund_id
        else reference(response) == refund.pk.hex)]
    if len(matches) > 1:
        note_error(refund, "ambiguous_provider_refund", review=True)
        return
    if matches:
        finish_wallet_refund(refund, matches[0])
        return
    if refund.provider_refund_id or not submit:
        return

    snapshot = client.get_payment(refund.checkout.provider_payment_id)
    snapshot.check_order(refund.checkout.pk, refund.checkout.amount)
    if snapshot.id != refund.checkout.provider_payment_id or not snapshot.captured:
        note_error(refund, "payment_requires_reconciliation", review=True)
        return
    # A portal refund outside this journal must be reconciled by an operator;
    # its disappearance/absence is never evidence that money can be re-issued.
    known = {item.provider_refund_id: item for item in refund.checkout.refunds.exclude(provider_refund_id=None)}
    if any(response.get("id") not in known for response in responses):
        note_error(refund, "external_refund_requires_reconciliation", review=True)
        return
    consumed = 0
    for response in responses:
        previous = known[response["id"]]
        finish_wallet_refund(previous, response)
        if response.get("status") not in RELEASED:
            consumed += previous.amount
    if consumed + refund.amount > refund.checkout.amount:
        note_error(refund, "provider_refund_ceiling_exceeded", review=True)
        return

    with transaction.atomic():
        lock_wallet(refund.request.wallet_id)
        locked = WalletRefund.objects.select_for_update().get(pk=refund.pk)
        if locked.status in TERMINAL or locked.provider_refund_id:
            return
        now = timezone.now()
        if locked.first_attempt_at and now - locked.first_attempt_at >= RETRY_WINDOW:
            note_error(locked, "idempotence_window_expired", review=True)
            return
        if locked.status == "REVIEW":
            return
        if locked.last_attempt_at and now - locked.last_attempt_at < ATTEMPT_LEASE:
            return
        locked.first_attempt_at = locked.first_attempt_at or now
        locked.last_attempt_at = now
        locked.status = "SENDING"
        locked.save(update_fields=["first_attempt_at", "last_attempt_at", "status", "updated_at"])
    # Persist the claim BEFORE any request. A crash or lost response cannot leave
    # an unrecorded external effect, and the provider also sees a stable UUID key.
    try:
        response = client.refund(refund.checkout.provider_payment_id, refund.amount, refund.pk,
                                 operation_reference=refund.pk.hex)
        finish_wallet_refund(refund, response)
    except CawlError:
        note_error(refund, "provider_response_inconsistent", review=True)
    except Exception:
        note_error(refund, "provider_outcome_unconfirmed")


def reconcile_pending_refunds(limit=100):
    count = 0
    refunds = WalletRefund.objects.exclude(status__in=TERMINAL).select_related(
        "checkout", "request").order_by("updated_at", "uuid")[:limit]
    for refund in list(refunds):
        try:
            reconcile_wallet_refund(refund)
        except CawlError:
            note_error(refund, "reconciliation_requires_review", review=True)
        except Exception:
            note_error(refund, "reconciliation_unavailable")
        count += 1
    return count
