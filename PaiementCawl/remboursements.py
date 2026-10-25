"""
Remboursement en ligne, par CAWL, du solde de la monnaie de l'événement.
/ Online CAWL refund of the event currency balance.

LOCALISATION : PaiementCawl/remboursements.py

RÈGLE (décision du 25 octobre 2026) :
- remboursable en ligne = le plus petit de : le solde de la monnaie du lieu, et ce qui a
  été rechargé PAR CAWL et pas encore remboursé. L'association ne rend jamais par carte
  plus que ce qu'elle a encaissé par carte ;
- le reste (rechargé sur place, espèces ou terminal) se rembourse au stand, en espèces
  (`WalletService.rembourser_en_especes`, existant) ;
- chaque remboursement part sur la carte qui a payé, sans dépasser ce paiement : les
  recharges sont remboursées de la plus récente à la plus ancienne ;
- un gala clôturé (monnaie désactivée ou archivée) n'est plus remboursé : sa monnaie
  n'est plus celle du produit de recharge actif (`trouver_le_produit_de_recharge_de_la_borne`
  ne retient qu'une monnaie active), donc rien n'est remboursable.
/ Online refundable = min(balance, CAWL top-ups not yet refunded), newest first, to the
paying card. The rest is refunded in cash at the stand. A closed event is never refunded.

Comptabilité, comme un vidage de carte à la caisse (laboutik/views.py,
`_ecrire_la_vente_du_vidage`) : une vente VIDAGE_CARTE avec un règlement POSITIF en
monnaie locale (les jetons repris, uuid de la transaction locale) et un règlement CAWL
NÉGATIF (l'argent rendu, relié au paiement de la recharge, référence du remboursement).
/ Accounting like a register card emptying, with a negative CAWL payment instead of cash.

Chaque remboursement est écrit dans SA transaction : un refus de CAWL sur une recharge
n'efface pas ceux déjà rendus sur les autres.
/ Each refund in its own transaction: a refusal does not erase those already done.
"""

import logging
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.db.models import Sum

logger = logging.getLogger(__name__)


@dataclass
class Remboursable:
    monnaie: object = None
    solde: int = 0
    en_ligne: int = 0
    sur_place: int = 0
    paiements: list = field(default_factory=list)  # [(Paiement_stripe, restant en centimes)]


def _deja_rembourse(paiement):
    from PaiementCawl.models import CawlRefund
    total = CawlRefund.objects.filter(payment__payment=paiement).exclude(
        status="REJECTED").aggregate(total=Sum("amount"))["total"]
    return total or 0


def _recharges_cawl(user, monnaie):
    from BaseBillet.models import Paiement_stripe, Product
    return Paiement_stripe.objects.filter(
        user=user,
        cawl_payment__isnull=False,
        status__in=[Paiement_stripe.VALID, Paiement_stripe.PAID, Paiement_stripe.PARTIALLY_REFUNDED],
        lignearticles__pricesold__productsold__product__methode_caisse=Product.RECHARGE_EUROS,
        lignearticles__pricesold__productsold__product__asset=monnaie,
    ).distinct().order_by("-order_date")


def calculer_le_remboursable(user):
    """
    Ce que la personne peut se faire rembourser en ligne, et ce qui reste au stand.
    / What the person can get refunded online, and what is left for the stand.
    """
    from fedow_core.services import WalletService
    from kiosk.credit import trouver_le_produit_de_recharge_de_la_borne

    produit, _tarif = trouver_le_produit_de_recharge_de_la_borne()
    if produit is None or user.wallet is None:
        return Remboursable()
    monnaie = produit.asset
    solde = WalletService.obtenir_solde(user.wallet, monnaie)
    paiements = []
    total_cawl_restant = 0
    for paiement in _recharges_cawl(user, monnaie):
        restant = int(paiement.montant_encaisse or 0) - _deja_rembourse(paiement)
        if restant > 0:
            paiements.append((paiement, restant))
            total_cawl_restant += restant
    en_ligne = min(solde, total_cawl_restant)
    return Remboursable(monnaie=monnaie, solde=solde, en_ligne=en_ligne,
                        sur_place=solde - en_ligne, paiements=paiements)


def rembourser_le_solde_en_ligne(user, ip="0.0.0.0"):
    """
    Rembourse en ligne ce qui peut l'être (voir la règle en tête du module).
    / Refunds online what can be (see the module rule).

    :return: (montant rendu en centimes, Remboursable relu après les remboursements)
    :raises CawlError: si CAWL refuse la PREMIÈRE recharge à rembourser (rien n'est rendu)
    """
    from BaseBillet.models import Paiement_stripe, PaymentMethod, SaleOrigin
    from BaseBillet.models_vente import Vente
    from BaseBillet.services_vente import ajouter_reglement, encaisser_vente, ouvrir_vente
    from fedow_core.models import Transaction
    from fedow_core.services import TransactionService, WalletService
    from PaiementCawl.models import CawlRefund
    from PaiementCawl.services import rembourser
    from payment_providers.cawl import CawlError

    rendu = 0
    for paiement, _restant in calculer_le_remboursable(user).paiements:
        try:
            with transaction.atomic():
                verrouille = Paiement_stripe.objects.select_for_update().get(pk=paiement.pk)
                # Relu sous verrou : un autre remboursement a pu passer entre-temps.
                # / Read again under lock: another refund may have happened meanwhile.
                a_jour = calculer_le_remboursable(user)
                monnaie = a_jour.monnaie
                restant = dict((p.pk, r) for p, r in a_jour.paiements).get(verrouille.pk, 0)
                montant = min(restant, a_jour.en_ligne)
                if montant <= 0:
                    continue
                numero = CawlRefund.objects.filter(payment__payment=verrouille).count()
                remboursement = rembourser(verrouille, montant, f"remboursement-solde-{verrouille.uuid}-{numero}")
                try:
                    reprise = TransactionService.creer(
                        sender=user.wallet, receiver=monnaie.wallet_origin, asset=monnaie,
                        montant_en_centimes=remboursement.amount, action=Transaction.REFUND,
                        tenant=connection.tenant, ip=ip, comment="Remboursement en ligne CAWL",
                        metadata={"payment_provider": "cawl", "paiement": str(verrouille.uuid),
                                  "remboursement": remboursement.id},
                    )
                    vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VIDAGE_CARTE, client=user)
                    ajouter_reglement(
                        vente, moyen=PaymentMethod.LOCAL_EURO, montant=remboursement.amount,
                        asset=monnaie.uuid, wallet=user.wallet, fedow_transaction_uuid=reprise.uuid,
                    )
                    ajouter_reglement(
                        vente, moyen=PaymentMethod.CAWL, montant=-remboursement.amount,
                        paiement_stripe=verrouille, reference_externe=remboursement.id,
                    )
                    encaisser_vente(vente)
                    tout_est_rendu = restant - remboursement.amount <= 0
                    Paiement_stripe.objects.filter(pk=verrouille.pk).update(
                        status=Paiement_stripe.REFUNDED if tout_est_rendu else Paiement_stripe.PARTIALLY_REFUNDED)
                except Exception as erreur:
                    logger.error(
                        f"Remboursement CAWL {remboursement.id} de {remboursement.amount} centimes "
                        f"(recharge {verrouille.uuid}) FAIT chez CAWL, mais rien n'est écrit en "
                        f"base : {erreur}. À rapprocher à la main."
                    )
                    raise
            rendu += remboursement.amount
        except CawlError:
            if rendu == 0:
                raise
            logger.warning(f"Remboursement en ligne interrompu après {rendu} centimes rendus.")
            break
    return rendu, calculer_le_remboursable(user)
