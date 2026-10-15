import logging
import os
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers

from payment_providers.cawl import (
    HOSTED_CHECKOUT_ABANDONED, HOSTED_CHECKOUT_EXPIRY_MARGIN_MINUTES, HOSTED_CHECKOUT_TIMEOUT_MINUTES,
    CawlConfiguration, CawlError, CawlGateway,
)

logger = logging.getLogger(__name__)

# FR : Tentatives finies sans encaissement. / Attempts that ended without collection.
FAILED_PAYMENT_STATES = {"REJECTED", "REJECTED_CAPTURE", "CANCELLED"}


def enabled():
    return getattr(settings, "PAYMENT_PROVIDER", "stripe") == "cawl"


def gateway():
    # FR : Un PSPID de gala ne doit jamais encaisser pour un autre tenant.
    # EN: A Gala merchant account must never collect for a different tenant.
    if os.environ.get("CAWL_TENANT_SCHEMA") != connection.schema_name:
        raise CawlError("CAWL n'est pas configuré pour cette organisation.")
    return CawlGateway(CawlConfiguration.from_environment(os.environ))


def checkout_expired(record, checkout_status):
    # FR : Sans paiement créé, une session abandonnée ou trop ancienne est expirée.
    # EN: Without a created payment, an abandoned or stale session is expired.
    if not record.hosted_checkout_id or checkout_status in HOSTED_CHECKOUT_ABANDONED:
        return True
    lifetime = timedelta(minutes=HOSTED_CHECKOUT_TIMEOUT_MINUTES + HOSTED_CHECKOUT_EXPIRY_MARGIN_MINUTES)
    return timezone.now() > record.created_at + lifetime


def check_account(record, client):
    config = client.configuration
    if record.merchant_id != config.merchant_id or record.test_mode != config.test_mode:
        raise CawlError("Le compte ou l'environnement CAWL du paiement a changé.")


class CreationPaiementCawl:
    def __init__(self, user, liste_ligne_article, metadata, reservation, source=None,
                 absolute_domain=None, success_url=None, cancel_url=None, invoice=None):
        from BaseBillet.models import Membership, Paiement_stripe, Reservation
        from PaiementCawl.models import CawlPayment

        if invoice:
            raise serializers.ValidationError(_("Une facture Stripe ne peut pas être encaissée par CAWL."))
        for line in liste_ligne_article:
            if line.pricesold.price.recurring_payment:
                raise serializers.ValidationError(_(
                    "Les renouvellements automatiques CAWL doivent être configurés avant cet encaissement."
                ))
        total = Decimal("0")
        for line in liste_ligne_article:
            total += Decimal(line.amount) * Decimal(str(line.qty))
        if total <= 0 or total != total.to_integral_value():
            raise serializers.ValidationError(_("Montant de paiement invalide."))
        client = gateway()
        from BaseBillet.models import Configuration
        if Configuration.get_solo().currency_code.upper() != 'EUR':
            raise serializers.ValidationError(_("Ce parcours CAWL est configuré en euros."))
        with transaction.atomic():
            if reservation:
                reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
                if reservation.paiements.filter(status__in=[Paiement_stripe.PENDING, Paiement_stripe.OPEN]).exists():
                    raise serializers.ValidationError(_("Un paiement est déjà en cours pour cette réservation."))
            for line in liste_ligne_article:
                if line.membership_id:
                    membership = Membership.objects.select_for_update().get(pk=line.membership_id)
                    if membership.stripe_paiement.filter(status__in=[Paiement_stripe.PENDING, Paiement_stripe.OPEN]).exists():
                        raise serializers.ValidationError(_("Un paiement est déjà en cours pour cette adhésion."))
            payment = Paiement_stripe.objects.create(
                user=user, metadata_stripe=metadata, reservation=reservation,
                source=source, status=Paiement_stripe.PENDING,
            )
            for line in liste_ligne_article:
                line.paiement_stripe = payment
                line.payment_method = "CW"
                line.save(update_fields=["paiement_stripe", "payment_method"])
                if line.membership_id:
                    line.membership.stripe_paiement.add(payment)
                    line.membership.payment_method = 'CW'
                    line.membership.save(update_fields=['payment_method'])
            if reservation:
                reservation.tickets.update(payment_method='CW')
            record = CawlPayment.objects.create(
                payment=payment, amount=int(total), merchant_id=client.configuration.merchant_id,
                test_mode=client.configuration.test_mode,
            )
        return_url = f"{absolute_domain}{payment.uuid}/{success_url}"
        domain = connection.tenant.get_primary_domain().domain
        try:
            checkout = client.create_checkout(
                reference=payment.uuid, amount=record.amount, return_url=return_url,
                webhook_url=f"https://{domain}/api/webhook_cawl/", email=user.email,
            )
        except Exception as error:
            # FR : Sans URL de paiement, l'acheteur ne peut rien régler : on libère la
            # commande pour qu'elle ne bloque pas un nouvel essai.
            # EN: No URL was handed out, so release the order instead of leaving it pending.
            logger.error("Création du paiement CAWL impossible pour %s : %s", payment.uuid, type(error).__name__)
            Paiement_stripe.objects.filter(pk=payment.pk, status=Paiement_stripe.PENDING).update(
                status=Paiement_stripe.CANCELED)
            raise serializers.ValidationError(_("Le paiement en ligne est momentanément indisponible.")) from error
        record.hosted_checkout_id = checkout.id
        record.checkout_url = checkout.url
        record.save(update_fields=["hosted_checkout_id", "checkout_url"])
        self.paiement_stripe_db = payment
        self.checkout_session = SimpleNamespace(id=checkout.id, stripe_id=None, url=checkout.url)


def checkout_session(payment):
    record = payment.cawl_payment
    client = gateway()
    check_account(record, client)
    checkout_status, snapshot = (client.get_checkout(record.hosted_checkout_id)
                                 if record.hosted_checkout_id else ("", None))
    if snapshot is not None:
        # A definitively rejected/cancelled payment cannot reuse its checkout.
        # Processing payments stay complete to prevent a second collection.
        status = "expired" if snapshot.status in FAILED_PAYMENT_STATES else "complete"
    elif checkout_expired(record, checkout_status):
        status = "expired"
    else:
        status = "open"
    return SimpleNamespace(
        id=record.hosted_checkout_id, url=record.checkout_url,
        status=status, payment_status="paid" if snapshot and snapshot.captured else "unpaid",
    )


def update_payment(payment, snapshot=None):
    from BaseBillet.models import LigneArticle, Paiement_stripe
    from PaiementCawl.models import CawlPayment

    record = payment.cawl_payment
    client = gateway()
    check_account(record, client)
    checkout_status = None
    if snapshot is None:
        if record.provider_payment_id:
            snapshot = client.get_payment(record.provider_payment_id)
        elif record.hosted_checkout_id:
            checkout_status, snapshot = client.get_checkout(record.hosted_checkout_id)
    if snapshot is None:
        if checkout_expired(record, checkout_status):
            # FR : Un paiement capturé plus tard reste accepté par update_payment.
            # EN: A later capture is still honoured: EXPIRE is not a final paid state.
            Paiement_stripe.objects.filter(
                pk=payment.pk, status__in=[Paiement_stripe.PENDING, Paiement_stripe.OPEN],
            ).update(status=Paiement_stripe.EXPIRE)
            payment.refresh_from_db(fields=["status"])
        return payment.status
    snapshot.check_order(payment.uuid, record.amount)
    # FR : Webhook et retour navigateur peuvent arriver en même temps.
    # EN: Serialize the webhook and browser return on the same payment row.
    with transaction.atomic():
        locked = Paiement_stripe.objects.select_for_update().get(pk=payment.pk)
        record = CawlPayment.objects.select_for_update().get(payment=locked)
        captured_states = {Paiement_stripe.PAID, Paiement_stripe.VALID, Paiement_stripe.REFUNDED, Paiement_stripe.NOTSYNC}
        if locked.status not in captured_states:
            record.provider_payment_id = snapshot.id
        record.provider_status = snapshot.status
        record.save(update_fields=["provider_payment_id", "provider_status"])
        if locked.status in captured_states or locked.traitement_en_cours:
            return locked.status
        if snapshot.captured:
            locked.status = Paiement_stripe.PAID
            locked.traitement_en_cours = True
            locked.last_action = timezone.now()
            locked.save()
            # FR : Les triggers pre_save valident aussi le paiement, mais le save
            # extérieur peut réécrire PAID. Refléter les lignes finales sans replay.
            # EN: Preserve final line state after nested pre_save payment updates.
            if (not locked.lignearticles.exclude(status=LigneArticle.VALID).exists()
                    and (locked.status != Paiement_stripe.VALID or locked.traitement_en_cours)):
                locked.status = Paiement_stripe.VALID
                locked.traitement_en_cours = False
                locked.save(update_fields=["status", "traitement_en_cours"])
            # FR : Crowds n'a pas de trigger de catégorie pour valider sa ligne.
            # EN: Crowds needs explicit finalisation of its uncategorised sale.
            from crowds.models import Contribution
            from crowds.tasks import email_contribution_paid_user

            contribution = Contribution.objects.select_for_update().filter(paiement_stripe=locked).first()
            if contribution and contribution.payment_status != Contribution.PaymentStatus.PAID:
                contribution.payment_status = Contribution.PaymentStatus.PAID
                contribution.paid_at = timezone.now()
                contribution.save(update_fields=["payment_status", "paid_at"])
                locked.lignearticles.update(status=LigneArticle.VALID)
                locked.status = Paiement_stripe.VALID
                locked.traitement_en_cours = False
                locked.save(update_fields=["status", "traitement_en_cours"])
                schema = connection.schema_name
                contribution_id = str(contribution.pk)
                transaction.on_commit(lambda: email_contribution_paid_user.delay(schema, contribution_id))
        elif snapshot.status in {"REJECTED", "REJECTED_CAPTURE"}:
            locked.status = Paiement_stripe.FAILED
            locked.lignearticles.update(status=LigneArticle.FAILED)
            locked.save(update_fields=["status"])
        elif snapshot.status == "CANCELLED":
            locked.status = Paiement_stripe.CANCELED
            locked.save(update_fields=["status"])
        return locked.status
