"""
Paiements en ligne CAWL, branchés sur les points d'entrée Stripe de TiBillet.
/ CAWL online payments, plugged into TiBillet's Stripe entry points.

LOCALISATION : PaiementCawl/services.py

Le reste du code de TiBillet ne change pas : le paiement reste un `Paiement_stripe`
(avec un `CawlPayment` à côté), la vente et ses règlements sont écrits par TiBillet à
partir de `montant_encaisse` et `moyen` (BaseBillet/services_vente.py), et les
remboursements passent par `partial_refund_payment` (PaiementStripe/utils.py), qui écrit
la vente d'avoir. Ce module ne fait que les appels à CAWL.
/ The rest of TiBillet is unchanged: TiBillet writes the sale from `montant_encaisse` and
`moyen`, and refunds go through `partial_refund_payment`. This module only calls CAWL.

Points d'entrée / Entry points :
- `creer_le_paiement` : appelé par `CreationPaiementStripe.__init__` ;
- `checkout_session` : appelé par `Paiement_stripe.get_checkout_session` ;
- `mettre_a_jour_le_statut` : appelé par `Paiement_stripe.update_checkout_status` ;
- `rembourser` : appelé par `partial_refund_payment`.
"""

import logging
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid5

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

# Tentatives terminées sans encaissement. / Attempts that ended without collection.
FAILED_PAYMENT_STATES = {"REJECTED", "REJECTED_CAPTURE", "CANCELLED"}


def enabled():
    return getattr(settings, "PAYMENT_PROVIDER", "stripe") == "cawl"


def tenants_autorises():
    """
    Les schémas des lieux autorisés à encaisser avec le compte CAWL de l'instance.
    / Schemas of the venues allowed to collect with the instance's CAWL account.

    Un seul contrat CAWL sert tous les événements de l'instance (galas ou kfet), mais
    le wizard peut créer d'autres lieux : sans cette liste, n'importe quel lieu créé
    sur l'instance encaisserait sur le compte de l'association.
    / One CAWL contract serves every event of the instance, but the wizard may create
    other venues: without this list any of them would collect on the association's account.

    `CAWL_TENANT_SCHEMAS` : liste séparée par des virgules (ex. « gala-2026,kfet-noel »).
    """
    valeur = os.environ.get("CAWL_TENANT_SCHEMAS", "")
    return {schema.strip() for schema in valeur.split(",") if schema.strip()}


def gateway():
    # Un lieu hors de la liste n'encaisse jamais sur le compte CAWL de l'instance.
    # / A venue outside the list never collects on the instance's CAWL account.
    if connection.schema_name not in tenants_autorises():
        raise CawlError("CAWL n'est pas configuré pour cette organisation.")
    return CawlGateway(CawlConfiguration.from_environment(os.environ))


def est_un_paiement_cawl(paiement):
    from PaiementCawl.models import CawlPayment
    return CawlPayment.objects.filter(payment_id=paiement.pk).exists()


def checkout_expired(record, checkout_status):
    # Sans paiement créé, une session abandonnée ou trop ancienne est expirée.
    # / Without a created payment, an abandoned or stale session is expired.
    if not record.hosted_checkout_id or checkout_status in HOSTED_CHECKOUT_ABANDONED:
        return True
    lifetime = timedelta(minutes=HOSTED_CHECKOUT_TIMEOUT_MINUTES + HOSTED_CHECKOUT_EXPIRY_MARGIN_MINUTES)
    return timezone.now() > record.created_at + lifetime


def check_account(record, client):
    config = client.configuration
    if record.merchant_id != config.merchant_id or record.test_mode != config.test_mode:
        raise CawlError("Le compte ou l'environnement CAWL du paiement a changé.")


def creer_le_paiement(createur):
    """
    Remplit un `CreationPaiementStripe` avec un paiement CAWL.
    / Fills a `CreationPaiementStripe` with a CAWL payment.

    Pose les mêmes attributs que le chemin Stripe, lus par les appelants :
    `paiement_stripe_db`, `checkout_session` (`id`, `url`, `stripe_id`), `invoice`.
    / Sets the same attributes the callers read on the Stripe path.

    Le `Paiement_stripe` est créé avec la vente d'origine (`vente`), la réservation et
    la réservation de créneau (`booking`), comme le chemin Stripe : la vente sera encaissée
    par TiBillet au passage à PAID. Le SEPA (`accept_sepa`) n'existe pas avec CAWL.
    / The payment is created with the original sale, the reservation and the booking,
    as on the Stripe path. SEPA does not exist with CAWL.
    """
    from BaseBillet.models import Configuration, Membership, Paiement_stripe, PaymentMethod, Reservation
    from PaiementCawl.models import CawlPayment

    if createur.invoice:
        raise serializers.ValidationError(_("Une facture Stripe ne peut pas être encaissée par CAWL."))
    for ligne in createur.liste_ligne_article:
        if ligne.pricesold.price.recurring_payment:
            raise serializers.ValidationError(_(
                "Les renouvellements automatiques ne sont pas disponibles avec CAWL."
            ))
    if Configuration.get_solo().currency_code.upper() != "EUR":
        raise serializers.ValidationError(_("Ce parcours CAWL est configuré en euros."))

    # Le montant à encaisser, en centimes : le total catalogue de chaque ligne (prix
    # unitaire × quantité), comme les line_items du chemin Stripe. Repli pour une ligne
    # sans total catalogue : `amount` (prix unitaire en centimes) × quantité.
    # / Amount in cents: each line's catalogue total, as Stripe line items.
    total = 0
    for ligne in createur.liste_ligne_article:
        if ligne.total_catalogue is not None:
            total += int(ligne.total_catalogue)
            continue
        quantite = ligne.qty
        if quantite != int(quantite):
            raise serializers.ValidationError(_("Montant de paiement invalide."))
        total += int(ligne.amount) * int(quantite)
    if total <= 0:
        raise serializers.ValidationError(_("Montant de paiement invalide."))

    client = gateway()
    with transaction.atomic():
        if createur.reservation:
            reservation = Reservation.objects.select_for_update().get(pk=createur.reservation.pk)
            if reservation.paiements.filter(status__in=[Paiement_stripe.PENDING, Paiement_stripe.OPEN]).exists():
                raise serializers.ValidationError(_("Un paiement est déjà en cours pour cette réservation."))
        for ligne in createur.liste_ligne_article:
            if ligne.membership_id:
                membership = Membership.objects.select_for_update().get(pk=ligne.membership_id)
                if membership.stripe_paiement.filter(
                        status__in=[Paiement_stripe.PENDING, Paiement_stripe.OPEN]).exists():
                    raise serializers.ValidationError(_("Un paiement est déjà en cours pour cette adhésion."))
        paiement = Paiement_stripe.objects.create(
            user=createur.user,
            metadata_stripe=createur.metadata_json,
            reservation=createur.reservation,
            booking=createur.booking,
            source=createur.source,
            status=Paiement_stripe.PENDING,
            vente=createur.vente,
        )
        # Les lignes sont écrites « Stripe carte » par leurs producteurs, avant de
        # connaître le prestataire : elles passent au moyen CAWL.
        # / Lines are written as "Stripe card" by their producers: they turn CAWL.
        for ligne in createur.liste_ligne_article:
            ligne.paiement_stripe = paiement
            ligne.payment_method = PaymentMethod.CAWL
            ligne.save()
            if ligne.membership_id:
                Membership.objects.filter(pk=ligne.membership_id).update(payment_method=PaymentMethod.CAWL)
        if createur.reservation:
            createur.reservation.tickets.update(payment_method=PaymentMethod.CAWL)
        record = CawlPayment.objects.create(
            payment=paiement, amount=total,
            merchant_id=client.configuration.merchant_id,
            test_mode=client.configuration.test_mode,
        )

    return_url = f"{createur.absolute_domain}{paiement.uuid}/{createur.success_url}"
    domaine = connection.tenant.get_primary_domain().domain
    try:
        checkout = client.create_checkout(
            reference=paiement.uuid, amount=record.amount, return_url=return_url,
            webhook_url=f"https://{domaine}/api/webhook_cawl/", email=createur.user.email,
        )
    except Exception as error:
        # Sans adresse de paiement, l'acheteur ne peut rien régler : on libère la
        # commande pour qu'elle ne bloque pas un nouvel essai.
        # / No URL was handed out: release the order so it does not block a retry.
        logger.error("Création du paiement CAWL impossible pour %s : %s", paiement.uuid, type(error).__name__)
        Paiement_stripe.objects.filter(pk=paiement.pk, status=Paiement_stripe.PENDING).update(
            status=Paiement_stripe.CANCELED)
        raise serializers.ValidationError(_("Le paiement en ligne est momentanément indisponible.")) from error

    record.hosted_checkout_id = checkout.id
    record.checkout_url = checkout.url
    record.save(update_fields=["hosted_checkout_id", "checkout_url"])
    # L'identifiant de la page CAWL prend la place de celui de la session Stripe : les
    # vues qui cherchent « un paiement déjà en cours » le retrouvent.
    # / The CAWL page id takes the Stripe session id's place, so "payment already in
    # progress" lookups find it.
    paiement.checkout_session_id_stripe = checkout.id
    paiement.checkout_session_url = checkout.url
    paiement.save(update_fields=["checkout_session_id_stripe", "checkout_session_url"])

    createur.paiement_stripe_db = paiement
    createur.checkout_session = SimpleNamespace(id=checkout.id, stripe_id=checkout.id, url=checkout.url)


def checkout_session(paiement):
    """
    L'état de la session de paiement, sous la forme lue par les appelants Stripe
    (`status` open/complete/expired, `payment_status` paid/unpaid, `url`).
    / The checkout state, shaped like the Stripe session the callers read.
    """
    record = paiement.cawl_payment
    client = gateway()
    check_account(record, client)
    checkout_status, snapshot = (client.get_checkout(record.hosted_checkout_id)
                                 if record.hosted_checkout_id else ("", None))
    if snapshot is not None:
        # Un paiement refusé ou annulé ne réutilise pas sa page ; un paiement en cours
        # reste « complete » pour empêcher un second encaissement.
        # / A rejected or cancelled payment cannot reuse its page; one in progress stays
        # complete to prevent a second collection.
        status = "expired" if snapshot.status in FAILED_PAYMENT_STATES else "complete"
    elif checkout_expired(record, checkout_status):
        status = "expired"
    else:
        status = "open"
    return SimpleNamespace(
        id=record.hosted_checkout_id, url=record.checkout_url, metadata=paiement.metadata_stripe,
        status=status, payment_status="paid" if snapshot and snapshot.captured else "unpaid",
    )


def mettre_a_jour_le_statut(paiement, snapshot=None):
    """
    Constate l'état du paiement chez CAWL et l'écrit sur le `Paiement_stripe`.
    / Reads the payment state at CAWL and writes it on the `Paiement_stripe`.

    Même chemin que le paiement Stripe constaté payé (`update_checkout_status`) :
    PAID, `traitement_en_cours`, `montant_encaisse` (montant CAPTURÉ, lu chez CAWL) et
    `moyen` CAWL, puis UN `save()`. Ce save déclenche les transitions de TiBillet
    (billets, adhésion, vente encaissée).
    / Same path as Stripe: PAID, amount captured read at CAWL, method CAWL, then one
    save() that triggers TiBillet's transitions (tickets, membership, settled sale).

    Le retour navigateur et le webhook peuvent arriver ensemble. La décision est prise
    sous verrou, et un paiement capturé est RÉSERVÉ (`traitement_en_cours`) avant que le
    verrou ne soit rendu : le second passage voit la réservation et s'arrête.
    Le `save()` final est fait HORS transaction, comme sur le chemin Stripe : certaines
    tâches Celery des déclencheurs (mail des billets) partent sans attendre le commit,
    elles doivent lire un état déjà écrit.
    / Decision under lock; a captured payment is CLAIMED before the lock is released.
    The final save() runs OUTSIDE a transaction, like the Stripe path: some trigger
    Celery tasks are sent without on_commit and must read committed state.
    """
    from BaseBillet.models import Paiement_stripe, PaymentMethod
    from PaiementCawl.models import CawlPayment

    client = gateway()
    record = paiement.cawl_payment
    check_account(record, client)
    checkout_status = None
    if snapshot is None:
        if record.provider_payment_id:
            snapshot = client.get_payment(record.provider_payment_id)
        elif record.hosted_checkout_id:
            checkout_status, snapshot = client.get_checkout(record.hosted_checkout_id)
    if snapshot is not None:
        snapshot.check_order(paiement.uuid, record.amount)

    statuts_deja_encaisses = {Paiement_stripe.PAID, Paiement_stripe.REFUNDED,
                              Paiement_stripe.PARTIALLY_REFUNDED, Paiement_stripe.NOTSYNC}
    capture = False
    with transaction.atomic():
        verrouille = Paiement_stripe.objects.select_for_update().get(pk=paiement.pk)
        record = CawlPayment.objects.select_for_update().get(payment=verrouille)
        if verrouille.status == Paiement_stripe.VALID or verrouille.traitement_en_cours:
            paiement.refresh_from_db()
            return verrouille.status

        if snapshot is None:
            nouveau_statut = (Paiement_stripe.EXPIRE if checkout_expired(record, checkout_status)
                              else Paiement_stripe.PENDING)
        else:
            if verrouille.status not in statuts_deja_encaisses:
                record.provider_payment_id = snapshot.id
            record.provider_status = snapshot.status
            record.save(update_fields=["provider_payment_id", "provider_status"])
            if verrouille.status in statuts_deja_encaisses:
                paiement.refresh_from_db()
                return verrouille.status
            if snapshot.captured:
                capture = True
                nouveau_statut = Paiement_stripe.PAID
                # Réservé sous verrou : un passage simultané s'arrête au garde ci-dessus.
                # / Claimed under lock: a concurrent pass stops at the guard above.
                Paiement_stripe.objects.filter(pk=verrouille.pk).update(traitement_en_cours=True)
            elif snapshot.status in FAILED_PAYMENT_STATES:
                nouveau_statut = Paiement_stripe.CANCELED
            else:
                nouveau_statut = Paiement_stripe.PENDING

    # Hors transaction, comme le chemin Stripe. / Outside a transaction, like Stripe.
    paiement.refresh_from_db()
    paiement.status = nouveau_statut
    if capture:
        paiement.last_action = timezone.now()
        paiement.traitement_en_cours = True
        # Posés AVANT le save() : la transition vers PAID écrit la vente avec eux.
        # / Set BEFORE save(): the PAID transition writes the sale with them.
        paiement.montant_encaisse = snapshot.amount
        paiement.moyen = PaymentMethod.CAWL
    try:
        paiement.save()
    except Exception:
        # La réservation est rendue : un prochain passage (webhook relivré, retour
        # navigateur) pourra reprendre le paiement.
        # / Release the claim so a later pass can process the payment again.
        if capture:
            Paiement_stripe.objects.filter(pk=paiement.pk, status__in=[
                Paiement_stripe.PENDING, Paiement_stripe.OPEN, Paiement_stripe.EXPIRE,
            ]).update(traitement_en_cours=False)
        raise

    paiement.refresh_from_db()
    if paiement.status in [Paiement_stripe.PAID, Paiement_stripe.VALID]:
        from PaiementCawl.recharges import crediter_la_recharge, est_une_recharge_en_ligne
        if est_une_recharge_en_ligne(paiement):
            crediter_la_recharge(paiement)
        else:
            finaliser_la_contribution_crowds(paiement)
        paiement.refresh_from_db()
    return paiement.status


def finaliser_la_contribution_crowds(paiement):
    """
    Une contribution Crowds payée : comme le webhook Stripe (ApiBillet/views.py),
    elle passe PAID, sa ligne VALID, et le mail de confirmation part. Le produit
    crowdfunding n'a pas de déclencheur de catégorie qui le ferait.
    / A paid Crowds contribution: same as the Stripe webhook, no category trigger does it.
    """
    from BaseBillet.models import LigneArticle, Paiement_stripe
    from crowds.models import Contribution
    from crowds.tasks import email_contribution_paid_user

    with transaction.atomic():
        contribution = Contribution.objects.select_for_update().filter(paiement_stripe=paiement).first()
        if contribution is None or contribution.payment_status == Contribution.PaymentStatus.PAID:
            return
        contribution.payment_status = Contribution.PaymentStatus.PAID
        contribution.paid_at = timezone.now()
        contribution.save(update_fields=["payment_status", "paid_at"])
        if contribution.ligne_article:
            contribution.ligne_article.status = LigneArticle.VALID
            contribution.ligne_article.save(update_fields=["status"])
        Paiement_stripe.objects.filter(pk=paiement.pk).update(
            traitement_en_cours=False, status=Paiement_stripe.VALID)
        schema = connection.schema_name
        contribution_id = str(contribution.pk)
        transaction.on_commit(lambda: email_contribution_paid_user.delay(schema, contribution_id))


def rembourser(paiement, montant_en_centimes, cle_d_idempotence):
    """
    Rembourse par CAWL une partie d'un paiement. Appelée par `partial_refund_payment`
    à la place de `stripe.Refund.create`, sous le verrou du paiement.
    / Refunds part of a payment through CAWL, instead of stripe.Refund.create.

    La clé d'idempotence de TiBillet (`remboursement-{uuid}-{n}`) devient un UUID
    stable : un nouvel essai après un échec renvoie le MÊME remboursement CAWL.
    / TiBillet's idempotency key becomes a stable UUID: a retry returns the same refund.

    Un refus de CAWL lève une erreur AVANT toute écriture. Le montant écrit est celui
    RENVOYÉ par CAWL. Un remboursement accepté puis refusé plus tard par la banque est
    suivi par la commande `reconcile_cawl_refunds` (alerte ERROR).
    / A CAWL refusal raises BEFORE anything is written. The written amount is the one
    returned by CAWL. A later bank rejection is caught by `reconcile_cawl_refunds`.

    :return: un objet avec `id`, `amount` et `status`, comme un `stripe.Refund`
    """
    from PaiementCawl.models import CawlRefund

    record = paiement.cawl_payment
    client = gateway()
    check_account(record, client)
    if not record.provider_payment_id:
        raise CawlError("Ce paiement CAWL doit être rapproché avant son remboursement.")

    operation_id = uuid5(UUID(str(paiement.uuid)), cle_d_idempotence)
    reponse = client.refund(record.provider_payment_id, int(montant_en_centimes), operation_id)

    statut = reponse.get("status", "")
    if statut == "REJECTED":
        raise CawlError("Le remboursement a été refusé par CAWL.")
    argent = reponse.get("refundOutput", {}).get("amountOfMoney", {})
    montant_rendu = argent.get("amount")
    identifiant = reponse.get("id")
    if not identifiant or type(montant_rendu) is not int or argent.get("currencyCode") != "EUR":
        raise CawlError("Réponse de remboursement CAWL incomplète.")

    CawlRefund.objects.update_or_create(
        operation_id=operation_id,
        defaults={
            "payment": record, "amount": montant_rendu, "provider_refund_id": identifiant,
            "status": statut, "accounted": True,
        },
    )
    logger.info(f"Remboursement CAWL {identifiant} : {statut}")
    return SimpleNamespace(id=identifiant, amount=montant_rendu, status=statut)


def rapprocher_le_remboursement(remboursement):
    """
    Relit chez CAWL l'état d'un remboursement déjà écrit en comptabilité. Un refus
    tardif est journalisé en ERROR : l'avoir est écrit mais l'argent n'est pas parti,
    à reprendre à la main.
    / Reads again at CAWL a refund already accounted. A late rejection is logged at
    ERROR: the credit note exists but the money did not leave, to handle by hand.
    """
    client = gateway()
    check_account(remboursement.payment, client)
    for reponse in client.get_refunds(remboursement.payment.provider_payment_id):
        if reponse.get("id") != remboursement.provider_refund_id:
            continue
        statut = reponse.get("status", "")
        if statut != remboursement.status:
            remboursement.status = statut
            remboursement.save(update_fields=["status"])
        if statut == "REJECTED":
            logger.error(
                f"Remboursement CAWL {remboursement.provider_refund_id} du paiement "
                f"{remboursement.payment_id} REFUSÉ par la banque après son écriture "
                f"comptable ({remboursement.amount} centimes) : à reprendre à la main."
            )
        return statut
    return None
