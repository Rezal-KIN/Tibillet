"""
Recharge en ligne par CAWL de la monnaie locale du lieu.
/ Online CAWL top-up of the venue's local currency.

LOCALISATION : PaiementCawl/recharges.py

La monnaie rechargée est celle de l'événement (le lieu) : l'Asset TLF du lieu, qui
ne se dépense que dans ce lieu (fedow_core : un lieu accepte ses monnaies et celles
de ses fédérations). Rien ne passe par la monnaie fédérée FED ni par le Fedow.
/ The topped-up currency is the venue's TLF asset, spendable only in this venue.

On reprend ce que TiBillet fait déjà pour la borne (kiosk/credit.py) :
- le produit « Recharge euros » du lieu, créé tout seul avec sa monnaie locale
  (fedow_core/signals.py), et son tarif libre (`trouver_le_produit_de_recharge_de_la_borne`) ;
- le crédit par `TransactionService.creer_recharge`, comme la caisse, UNE seule fois.
Et ce que fait Crowds pour une vente en ligne hors panier (crowds/views.py) : une vente,
un article (`ajouter_article`), puis `CreationPaiementStripe`, qui passe par CAWL.
/ Reuses the kiosk top-up product and credit function, and the Crowds online sale path.

Comptabilité : l'article est une recharge (hors chiffre d'affaires, TVA 0, compte de
dette envers les clients), le règlement est CAWL : TiBillet l'écrit tout seul.
/ Accounting: a top-up item (out of revenue, 0 % VAT), settled by CAWL.
"""

import logging
from decimal import Decimal

from django.db import connection, transaction
from django.utils.translation import gettext as _
from rest_framework import serializers

logger = logging.getLogger(__name__)

# Bornes d'une recharge en ligne, en centimes. / Online top-up bounds, in cents.
MONTANT_MINIMUM = 100
MONTANT_MAXIMUM = 50000


def est_une_recharge_en_ligne(paiement):
    from BaseBillet.models import Product
    return paiement.lignearticles.filter(
        pricesold__productsold__product__methode_caisse=Product.RECHARGE_EUROS,
    ).exists()


def recharge_en_ligne_disponible():
    """Le lieu a une monnaie locale active et son produit de recharge à tarif libre.
    / The venue has an active local currency and its free-price top-up product."""
    from kiosk.credit import trouver_le_produit_de_recharge_de_la_borne
    produit, tarif_libre = trouver_le_produit_de_recharge_de_la_borne()
    return tarif_libre is not None


def creer_la_recharge_en_ligne(user, montant_en_centimes, domaine):
    """
    Ouvre la vente de la recharge et la page de paiement CAWL.
    / Opens the top-up sale and the CAWL payment page.

    :param user: la personne qui recharge (son portefeuille sera crédité)
    :param montant_en_centimes: int, entre MONTANT_MINIMUM et MONTANT_MAXIMUM
    :param domaine: domaine du lieu, pour l'adresse de retour
    :return: l'adresse de la page de paiement CAWL
    """
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import LigneArticle, Paiement_stripe, PaymentMethod, SaleOrigin
    from BaseBillet.models_vente import Vente
    from BaseBillet.services_vente import ajouter_article, ouvrir_vente
    from fedow_connect.fedow_api import FedowAPI
    from kiosk.credit import trouver_le_produit_de_recharge_de_la_borne
    from laboutik.views import _taux_tva_de_la_ligne_de_caisse
    from PaiementStripe.views import CreationPaiementStripe

    if type(montant_en_centimes) is not int or not MONTANT_MINIMUM <= montant_en_centimes <= MONTANT_MAXIMUM:
        raise serializers.ValidationError(_("Montant de recharge invalide."))
    produit, tarif_libre = trouver_le_produit_de_recharge_de_la_borne()
    if tarif_libre is None:
        raise serializers.ValidationError(_("La recharge en ligne n'est pas disponible pour cet événement."))

    # Le portefeuille de la personne : celui que la caisse débite quand sa carte est
    # liée (laboutik/views.py, _obtenir_ou_creer_wallet).
    # / The person's wallet: the one the register debits once their card is linked.
    if user.wallet is None:
        FedowAPI().wallet.get_or_create_wallet(user)
        user.refresh_from_db()

    price_sold = get_or_create_price_sold(
        tarif_libre, custom_amount=(Decimal(montant_en_centimes) / 100).quantize(Decimal("0.01")),
    )
    with transaction.atomic():
        vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=user)
        ligne = ajouter_article(
            vente,
            pricesold=price_sold,
            quantite=1,
            prix_unitaire=montant_en_centimes,
            taux_tva=_taux_tva_de_la_ligne_de_caisse(produit, PaymentMethod.CAWL),
            payment_method=PaymentMethod.CAWL,
            sale_origin=SaleOrigin.LESPASS,
        )
    createur = CreationPaiementStripe(
        user=user,
        liste_ligne_article=[ligne],
        metadata={"tenant": f"{connection.tenant.uuid}", "recharge_en_ligne": str(produit.asset_id)},
        reservation=None,
        source=Paiement_stripe.FRONT_BILLETTERIE,
        success_url="return_refill_wallet/",
        cancel_url="return_refill_wallet/",
        absolute_domain=f"https://{domaine}/my_account/",
        vente=vente,
    )
    createur.paiement_stripe_db.lignearticles.all().update(status=LigneArticle.UNPAID)
    return createur.checkout_session.url


def crediter_la_recharge(paiement):
    """
    Crédite la monnaie du lieu d'une recharge payée, UNE seule fois par paiement.
    / Credits the venue currency of a paid top-up, ONCE per payment.

    Appelée par `mettre_a_jour_le_statut` (PaiementCawl/services.py) dès que le
    paiement est payé : retour navigateur et webhook passent tous les deux par elle.
    Sous verrou du paiement : une transaction REFILL portant l'uuid du paiement
    (`checkout_stripe`) existe déjà → rien à faire.
    / Called once the payment is paid; under the payment lock, an existing REFILL
    transaction with this payment's uuid means nothing to do.

    Le montant crédité est le montant ENCAISSÉ chez CAWL (`montant_encaisse`).
    / The credited amount is the amount COLLECTED at CAWL.

    :return: la Transaction de recharge, ou None
    """
    from BaseBillet.models import LigneArticle, Paiement_stripe, Product
    from fedow_core.models import Transaction
    from fedow_core.services import TransactionService

    with transaction.atomic():
        verrouille = Paiement_stripe.objects.select_for_update().get(pk=paiement.pk)
        deja_creditee = Transaction.objects.filter(
            checkout_stripe=verrouille.uuid, action=Transaction.REFILL,
        ).first()
        if deja_creditee is not None:
            return deja_creditee
        if verrouille.status not in [Paiement_stripe.PAID, Paiement_stripe.VALID]:
            return None
        ligne = verrouille.lignearticles.select_related(
            "pricesold__productsold__product__asset",
        ).get(pricesold__productsold__product__methode_caisse=Product.RECHARGE_EUROS)
        asset = ligne.pricesold.productsold.product.asset
        destinataire = verrouille.user.wallet
        # Gala clôturé (monnaie désactivée ou archivée) : sa comptabilité est close, on
        # ne crédite plus rien. Un paiement capturé trop tard est à rembourser à la main.
        # / Closed event (currency inactive or archived): nothing is credited anymore.
        if asset is not None and (not asset.active or asset.archive):
            logger.error(
                f"Recharge CAWL {verrouille.uuid} payée après la clôture de la monnaie "
                f"{asset.name} : NON créditée, à rembourser à la main."
            )
            return None
        if asset is None or destinataire is None:
            logger.error(
                f"Recharge CAWL {verrouille.uuid} payée mais NON créditée : monnaie ou "
                f"portefeuille absent. À créditer ou rembourser à la main."
            )
            return None
        recharge = TransactionService.creer_recharge(
            sender_wallet=asset.wallet_origin,
            receiver_wallet=destinataire,
            asset=asset,
            montant_en_centimes=int(verrouille.montant_encaisse),
            tenant=connection.tenant,
            checkout_stripe_uuid=verrouille.uuid,
            comment="Recharge en ligne CAWL",
            metadata={"payment_provider": "cawl", "paiement": str(verrouille.uuid)},
        )
        # Le produit de recharge n'a pas de déclencheur de catégorie : la ligne et le
        # paiement sont validés ici, comme la contribution Crowds.
        # / The top-up product has no category trigger: line and payment validated here.
        verrouille.lignearticles.filter(pk=ligne.pk).update(status=LigneArticle.VALID)
        Paiement_stripe.objects.filter(pk=verrouille.pk).update(
            status=Paiement_stripe.VALID, traitement_en_cours=False,
        )
    logger.info(f"Recharge CAWL {paiement.uuid} : {recharge.amount} centimes de {asset.name} crédités")
    return recharge
