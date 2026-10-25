import os
from datetime import timedelta
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from fedow_core.models import Asset, Configuration, Token, Transaction, Wallet
from fedow_core.serializers import TransactionW2W
from payment_providers.cawl import (
    HOSTED_CHECKOUT_EXPIRY_MARGIN_MINUTES, HOSTED_CHECKOUT_TIMEOUT_MINUTES,
    CawlConfiguration, CawlError, CawlGateway,
)
from cawl_fedow.models import Checkout


def gateway():
    return CawlGateway(CawlConfiguration.from_environment(os.environ))


class VerifiedCawlRefill(TransactionW2W):
    """Crédit interne après vérification CAWL. / Verified internal refill only."""

    def get_action(self, attrs):
        checkout = self.context["cawl_checkout"]
        if (attrs["sender"].is_primary()
                and attrs["asset"].wallet_origin_id == attrs["sender"].pk
                and attrs["receiver"].pk == checkout.wallet_id
                and attrs["asset"].pk == checkout.asset_id
                and attrs["amount"] == checkout.amount
                and attrs.get("action") == Transaction.REFILL):
            return Transaction.REFILL
        raise serializers.ValidationError("Recharge CAWL incohérente.")


def create_checkout(request, amount):
    client = gateway()
    config = Configuration.get_solo()
    # FR : On conserve l'asset et les soldes existants. Le nom historique STRIPE_FED_FIAT
    # ne déclenche aucun appel Stripe dans ce nouveau parcours.
    # EN: Preserve the existing FED asset and balances; its legacy name makes no API call.
    asset = Asset.objects.get(wallet_origin=config.primary_wallet, category=Asset.STRIPE_FED_FIAT, archive=False)
    domain = request.place.lespass_domain
    if not domain or "/" in domain or ":" in domain:
        raise CawlError("Le domaine de retour du lieu est invalide.")
    with transaction.atomic():
        Wallet.objects.filter(pk=request.wallet.pk).update(name=F('name'))
        Wallet.objects.select_for_update().get(pk=request.wallet.pk)
        existing = Checkout.objects.filter(
            wallet=request.wallet, place=request.place, amount=amount, refill__isnull=True,
            # FR : On ne réutilise qu'une page encore valide pendant toute la marge.
            # EN: Only reuse a hosted page that stays valid for the whole margin.
            created_at__gte=timezone.now() - timedelta(
                minutes=HOSTED_CHECKOUT_TIMEOUT_MINUTES - HOSTED_CHECKOUT_EXPIRY_MARGIN_MINUTES),
        ).exclude(provider_status__in=['REJECTED', 'REJECTED_CAPTURE', 'CANCELLED']).first()
        if existing:
            if (existing.merchant_id != client.configuration.merchant_id
                    or existing.test_mode != client.configuration.test_mode):
                raise CawlError('Une demande existe sur un autre compte ou environnement CAWL.')
            if not existing.checkout_url:
                raise CawlError('Une demande de paiement est déjà en cours.')
            return existing
        checkout = Checkout.objects.create(
            wallet=request.wallet, place=request.place, asset=asset, amount=amount,
            merchant_id=client.configuration.merchant_id, test_mode=client.configuration.test_mode,
        )
    try:
        result = client.create_checkout(
            reference=checkout.uuid, amount=amount,
            return_url=f"https://{domain}/my_account/{checkout.uuid}/return_refill_wallet/",
            webhook_url=f"https://{os.environ['DOMAIN']}/webhook_cawl/",
            email=request.wallet.user.email,
        )
    except Exception as error:
        # FR : Aucune URL n'a été remise : la demande ne doit pas bloquer les essais suivants.
        # EN: No URL was handed out; do not let this request block later attempts.
        Checkout.objects.filter(pk=checkout.pk, refill__isnull=True, hosted_checkout_id__isnull=True).delete()
        raise CawlError("Création du paiement CAWL impossible.") from error
    checkout.hosted_checkout_id = result.id
    checkout.checkout_url = result.url
    checkout.save(update_fields=["hosted_checkout_id", "checkout_url"])
    return checkout


def credit_checkout(checkout, request, snapshot=None):
    client = gateway()
    if (checkout.merchant_id != client.configuration.merchant_id
            or checkout.test_mode != client.configuration.test_mode):
        raise CawlError("Compte ou environnement CAWL différent du paiement initial.")
    if snapshot is None:
        if checkout.provider_payment_id:
            snapshot = client.get_payment(checkout.provider_payment_id)
        else:
            snapshot = client.get_checkout_payment(checkout.hosted_checkout_id)
    if snapshot is None:
        return False
    snapshot.check_order(checkout.uuid, checkout.amount)
    with transaction.atomic():
        # FR : SQLite ne fait pas de SELECT FOR UPDATE. Cette écriture prend
        # son verrou avant toute lecture qui précède le crédit monétaire.
        # EN: SQLite needs an initial write to serialize concurrent credits.
        Checkout.objects.filter(pk=checkout.pk).update(lock_version=F("lock_version") + 1)
        locked = Checkout.objects.select_for_update().select_related("wallet", "place", "asset").get(pk=checkout.pk)
        if not locked.refill_id:
            locked.provider_payment_id = snapshot.id
        locked.provider_status = snapshot.status
        locked.save(update_fields=["provider_payment_id", "provider_status"])
        if locked.refill_id:
            return True
        if not snapshot.captured:
            return False
        if locked.asset.archive:
            raise CawlError("L'asset de cette recharge est archivé.")
        config = Configuration.get_solo()
        if locked.asset.wallet_origin_id != config.primary_wallet_id:
            raise CawlError("Le portefeuille émetteur a changé.")
        Token.objects.get_or_create(wallet=config.primary_wallet, asset=locked.asset)
        Token.objects.get_or_create(wallet=locked.wallet, asset=locked.asset)
        request.place = locked.place
        validator = VerifiedCawlRefill(data={
            "sender": str(config.primary_wallet_id),
            "receiver": str(locked.wallet_id), "asset": str(locked.asset_id),
            "amount": locked.amount, "action": Transaction.REFILL,
            "metadata": {
                "payment_provider": "cawl", "cawl_checkout_uuid": str(locked.uuid),
                "cawl_payment_id": snapshot.id, "merchant_id": locked.merchant_id,
                "test_mode": locked.test_mode,
            },
        }, context={"request": request, "cawl_checkout": locked})
        validator.is_valid(raise_exception=True)
        # FR : Le serializer natif écrit CREATION et REFILL dans le même bloc.
        # EN: Native validation writes the mint/refill pair in one transaction.
        locked.refill = validator.transaction
        locked.save(update_fields=["refill"])
        return True
