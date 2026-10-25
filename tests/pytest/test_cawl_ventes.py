"""
Tests pytest : ventes en ligne par CAWL, avec la comptabilité de TiBillet.
/ Pytest tests: CAWL online sales, with TiBillet's accounting.

LOCALISATION : tests/pytest/test_cawl_ventes.py

Code testé / Tested code : PaiementCawl/services.py, PaiementCawl/views.py, et ses
accroches (PaiementStripe/views.py `CreationPaiementStripe`, BaseBillet/models.py
`Paiement_stripe.update_checkout_status`, PaiementStripe/utils.py `partial_refund_payment`).

La commande passe par le vrai panier (`CommandeService.materialiser`), DANS le processus
de test : `PAYMENT_PROVIDER=cawl` y est posé par la fixture `cawl`, et CAWL est remplacé
par `FausseCawl` (aucun appel réseau). Le serveur de dev reste en mode Stripe.
/ The order goes through the real cart, in the test process; CAWL is replaced by a fake.

Lancer / Run :
  docker exec lespass_django poetry run pytest tests/pytest/test_cawl_ventes.py -q
"""
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from fabriques_reservation import creer_evenement_et_produit, identifiant_aleatoire, materialiser_panier

from payment_providers.cawl import CawlError, HostedCheckout, PaymentSnapshot


class FausseCawl:
    """
    Remplace `CawlGateway` : garde les pages de paiement, les paiements et les
    remboursements en mémoire. / Replaces CawlGateway, all in memory.
    """

    def __init__(self, configuration):
        self.configuration = configuration
        self.pages = {}
        self.paiements = {}
        self.remboursements = []
        self.refuser_les_remboursements = False

    def create_checkout(self, reference, amount, return_url, webhook_url, email):
        identifiant = f"hc-{uuid4().hex[:12]}"
        self.pages[identifiant] = {"reference": str(reference), "amount": amount, "payment_id": None}
        return HostedCheckout(identifiant, f"https://payment.preprod.cawl-solutions.fr/{identifiant}", "mac")

    def capturer(self, paiement, montant=None, statut="CAPTURED"):
        """L'acheteur paie sur la page CAWL. / The buyer pays on the CAWL page."""
        page = self.pages[paiement.cawl_payment.hosted_checkout_id]
        identifiant = f"pay-{uuid4().hex[:12]}"
        page["payment_id"] = identifiant
        self.paiements[identifiant] = PaymentSnapshot(
            id=identifiant, reference=page["reference"],
            amount=page["amount"] if montant is None else montant,
            currency="EUR", status=statut,
        )
        return identifiant

    def get_checkout(self, hosted_checkout_id):
        page = self.pages.get(hosted_checkout_id)
        if page is None or page["payment_id"] is None:
            return "IN_PROGRESS", None
        return "PAYMENT_CREATED", self.paiements[page["payment_id"]]

    def get_checkout_payment(self, hosted_checkout_id):
        return self.get_checkout(hosted_checkout_id)[1]

    def get_payment(self, payment_id):
        return self.paiements[payment_id]

    def refund(self, payment_id, amount, operation_id, operation_reference=None):
        self.remboursements.append({"payment_id": payment_id, "amount": amount, "operation_id": str(operation_id)})
        statut = "REJECTED" if self.refuser_les_remboursements else "REFUND_REQUESTED"
        return {
            "id": f"rf-{operation_id}", "status": statut,
            "refundOutput": {"amountOfMoney": {"amount": amount, "currencyCode": "EUR"}},
        }

    def get_refunds(self, payment_id):
        return [{"id": f"rf-{r['operation_id']}", "status": "REFUNDED"}
                for r in self.remboursements if r["payment_id"] == payment_id]

    def verify_webhook(self, body, headers):
        return json.loads(body)


@pytest.fixture
def cawl(settings, monkeypatch, tenant):
    """Instance CAWL, lieu autorisé, CAWL simulé. / CAWL instance, allowed venue, fake CAWL."""
    from payment_providers.cawl import CawlConfiguration

    settings.PAYMENT_PROVIDER = "cawl"
    for variable, valeur in {
        "CAWL_MERCHANT_ID": "marchand-test", "CAWL_API_KEY_ID": "cle", "CAWL_API_SECRET": "secret",
        "CAWL_WEBHOOK_KEY_ID": "cle-webhook", "CAWL_WEBHOOK_SECRET": "secret-webhook", "CAWL_TEST": "1",
        "CAWL_TENANT_SCHEMAS": f"autre-lieu, {tenant.schema_name}",
    }.items():
        monkeypatch.setenv(variable, valeur)
    fausse_cawl = FausseCawl(CawlConfiguration.from_environment(__import__("os").environ))
    monkeypatch.setattr("PaiementCawl.services.CawlGateway", lambda configuration: fausse_cawl)
    return fausse_cawl


@pytest.fixture
def evenement(api_client, auth_headers):
    return creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())


def commander(evenement, qty):
    event_uuid, price_uuid = evenement
    email = f"test+cawl{identifiant_aleatoire()}@mock.test"
    reservation = materialiser_panier(email, event_uuid, price_uuid, qty)
    return reservation, reservation.commande.paiement_stripe


def reglements(vente, moyen=None):
    from BaseBillet.models_vente import Reglement
    resultat = Reglement.objects.filter(vente=vente)
    if moyen:
        resultat = resultat.filter(moyen=moyen)
    return list(resultat)


class TestAchatCawl:

    def test_la_commande_cree_une_page_cawl_au_montant_du_catalogue(self, cawl, evenement, tenant):
        """Le paiement porte la page CAWL, ses lignes passent au moyen CAWL.
        / The payment carries the CAWL page; its lines turn CAWL."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle, PaymentMethod

        with tenant_context(tenant):
            reservation, paiement = commander(evenement, qty=2)
            record = paiement.cawl_payment
            lignes = LigneArticle.objects.filter(paiement_stripe=paiement)
            total_catalogue = sum(ligne.total_catalogue for ligne in lignes)

            assert record.amount == total_catalogue > 0
            assert record.hosted_checkout_id in cawl.pages
            assert paiement.checkout_session_id_stripe == record.hosted_checkout_id
            assert all(ligne.payment_method == PaymentMethod.CAWL for ligne in lignes)

    def test_le_paiement_capture_encaisse_la_vente_au_moyen_cawl(self, cawl, evenement, tenant):
        """Capturé chez CAWL : PAID puis vente REGLEE, UN règlement CAWL au montant capturé.
        Un second passage (webhook après le retour navigateur) n'écrit rien de plus.
        / Captured: sale settled with ONE CAWL payment; a replay writes nothing more."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe, PaymentMethod
        from BaseBillet.models_vente import Vente

        with tenant_context(tenant):
            reservation, paiement = commander(evenement, qty=2)
            montant = paiement.cawl_payment.amount
            cawl.capturer(paiement)

            statut = paiement.update_checkout_status()
            assert statut in [Paiement_stripe.PAID, Paiement_stripe.VALID]
            paiement.refresh_from_db()
            assert paiement.montant_encaisse == montant
            assert paiement.moyen == PaymentMethod.CAWL

            vente = Vente.objects.get(pk=paiement.vente_id)
            assert vente.statut == Vente.Statut.REGLEE
            assert [r.montant for r in reglements(vente, PaymentMethod.CAWL)] == [montant]

            paiement.update_checkout_status()
            assert [r.montant for r in reglements(vente, PaymentMethod.CAWL)] == [montant]

    def test_un_paiement_pas_encore_capture_reste_en_attente(self, cawl, evenement, tenant):
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe

        with tenant_context(tenant):
            reservation, paiement = commander(evenement, qty=1)
            assert paiement.update_checkout_status() == Paiement_stripe.PENDING
            cawl.capturer(paiement, statut="PENDING_CAPTURE")
            assert paiement.update_checkout_status() == Paiement_stripe.PENDING
            paiement.refresh_from_db()
            assert paiement.montant_encaisse is None

    def test_un_montant_capture_different_est_refuse(self, cawl, evenement, tenant):
        """Le montant CAWL doit être celui de la commande : rien n'est encaissé sinon.
        / The CAWL amount must match the order: nothing is settled otherwise."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe

        with tenant_context(tenant):
            reservation, paiement = commander(evenement, qty=1)
            cawl.capturer(paiement, montant=paiement.cawl_payment.amount - 1)
            with pytest.raises(CawlError):
                paiement.update_checkout_status()
            paiement.refresh_from_db()
            assert paiement.status == Paiement_stripe.PENDING
            assert paiement.montant_encaisse is None

    def test_un_lieu_hors_de_la_liste_n_encaisse_pas(self, cawl, evenement, tenant, monkeypatch):
        """Un seul contrat CAWL, mais seuls les lieux listés encaissent.
        / One CAWL contract, but only listed venues collect."""
        from django_tenants.utils import tenant_context
        from PaiementCawl.models import CawlPayment
        from PaiementCawl.services import gateway

        monkeypatch.setenv("CAWL_TENANT_SCHEMAS", "autre-lieu")
        with tenant_context(tenant):
            with pytest.raises(CawlError):
                gateway()
            avant = CawlPayment.objects.count()
            with pytest.raises(Exception):
                commander(evenement, qty=1)
            assert CawlPayment.objects.count() == avant
            assert cawl.pages == {}


def reservation_payee_par_cawl(cawl, evenement, qty):
    from BaseBillet.models import Reservation
    reservation, paiement = commander(evenement, qty=qty)
    cawl.capturer(paiement)
    paiement.update_checkout_status()
    reservation.refresh_from_db()
    paiement.refresh_from_db()
    assert reservation.status in [Reservation.PAID, Reservation.VALID], reservation.status
    return reservation, paiement


class TestRemboursementCawl:

    def test_un_billet_puis_le_reste_ecrivent_deux_avoirs_cawl(self, cawl, evenement, tenant):
        """Un billet, puis le reste : deux remboursements CAWL, deux ventes d'avoir avec un
        règlement CAWL négatif au montant rendu par CAWL, paiement « remboursé » à la fin.
        / One ticket then the rest: two CAWL refunds, two credit notes, payment REFUNDED."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe, PaymentMethod, Ticket
        from BaseBillet.models_vente import Vente

        with tenant_context(tenant):
            reservation, paiement = reservation_payee_par_cawl(cawl, evenement, qty=2)
            montant = paiement.cawl_payment.amount
            prix_un_billet = montant // 2

            reservation.cancel_and_refund_ticket(reservation.tickets.order_by("pk").first())
            paiement.refresh_from_db()
            assert paiement.status == Paiement_stripe.PARTIALLY_REFUNDED
            reservation.refresh_from_db()
            reservation.cancel_and_refund_resa()
            paiement.refresh_from_db()
            assert paiement.status == Paiement_stripe.REFUNDED

            assert [r["amount"] for r in cawl.remboursements] == [prix_un_billet, montant - prix_un_billet]
            avoirs = Vente.objects.filter(vente_liee_id=paiement.vente_id, nature=Vente.Nature.AVOIR)
            assert avoirs.count() == 2
            montants_rendus = sorted(r.montant for avoir in avoirs for r in reglements(avoir, PaymentMethod.CAWL))
            assert montants_rendus == sorted([-prix_un_billet, -(montant - prix_un_billet)])
            references = {r.reference_externe for avoir in avoirs for r in reglements(avoir, PaymentMethod.CAWL)}
            assert references == {f"rf-{r['operation_id']}" for r in cawl.remboursements}
            assert all(billet.status == Ticket.CANCELED for billet in reservation.tickets.all())

    def test_un_refus_de_cawl_n_ecrit_rien(self, cawl, evenement, tenant):
        """CAWL refuse : erreur, aucun avoir, le billet reste actif.
        / CAWL refuses: error, no credit note, the ticket stays active."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Ticket
        from BaseBillet.models_vente import Vente

        with tenant_context(tenant):
            reservation, paiement = reservation_payee_par_cawl(cawl, evenement, qty=1)
            cawl.refuser_les_remboursements = True
            billet = reservation.tickets.get()
            with pytest.raises(Exception):
                reservation.cancel_and_refund_ticket(billet)
            assert not Vente.objects.filter(vente_liee_id=paiement.vente_id, nature=Vente.Nature.AVOIR).exists()
            billet.refresh_from_db()
            assert billet.status != Ticket.CANCELED

    def test_un_nouvel_essai_reprend_la_meme_operation_cawl(self, cawl, evenement, tenant):
        """Même clé d'idempotence TiBillet : même identifiant d'opération chez CAWL.
        / Same TiBillet idempotency key: same CAWL operation id."""
        from django_tenants.utils import tenant_context
        from PaiementCawl.services import rembourser

        with tenant_context(tenant):
            reservation, paiement = reservation_payee_par_cawl(cawl, evenement, qty=1)
            cle = f"remboursement-{paiement.uuid}-0"
            premier = rembourser(paiement, 100, cle)
            second = rembourser(paiement, 100, cle)
            assert premier.id == second.id
            assert cawl.remboursements[0]["operation_id"] == cawl.remboursements[1]["operation_id"]
            autre = rembourser(paiement, 100, f"remboursement-{paiement.uuid}-1")
            assert autre.id != premier.id


class TestWebhookCawl:

    def appeler(self, evenement_cawl):
        from django.test import RequestFactory
        from PaiementCawl.views import webhook
        request = RequestFactory().post(
            "/api/webhook_cawl/", data=json.dumps(evenement_cawl), content_type="application/json",
        )
        return webhook(request)

    def test_le_webhook_encaisse_une_seule_fois(self, cawl, evenement, tenant):
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe, PaymentMethod
        from BaseBillet.models_vente import Vente

        with tenant_context(tenant):
            reservation, paiement = commander(evenement, qty=1)
            identifiant = cawl.capturer(paiement)
            evenement_cawl = {"id": str(uuid4()), "type": "payment.captured", "payment": {"id": identifiant}}

            assert self.appeler(evenement_cawl).status_code == 200
            paiement.refresh_from_db()
            assert paiement.status in [Paiement_stripe.PAID, Paiement_stripe.VALID]
            assert self.appeler(evenement_cawl).status_code == 200
            vente = Vente.objects.get(pk=paiement.vente_id)
            assert len(reglements(vente, PaymentMethod.CAWL)) == 1

    def test_un_paiement_d_un_autre_marchand_est_ignore(self, cawl, evenement, tenant):
        """Le paiement n'est cherché que pour le marchand et l'environnement de l'instance.
        / The payment is only looked up for the instance's merchant and environment."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe
        from PaiementCawl.models import CawlPayment

        with tenant_context(tenant):
            reservation, paiement = commander(evenement, qty=1)
            CawlPayment.objects.filter(payment=paiement).update(merchant_id="autre-marchand")
            identifiant = cawl.capturer(paiement)
            evenement_cawl = {"id": str(uuid4()), "type": "payment.captured", "payment": {"id": identifiant}}
            assert self.appeler(evenement_cawl).status_code == 200
            paiement.refresh_from_db()
            assert paiement.status == Paiement_stripe.PENDING


class TestStripeDesactive:

    def test_aucune_cle_stripe_en_mode_cawl(self, cawl, tenant):
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Configuration
        from root_billet.models import RootConfiguration

        assert RootConfiguration.get_solo().get_stripe_api() is None
        with tenant_context(tenant):
            assert Configuration.get_solo().get_stripe_connect_account() is None


class TestAdhesionCawl:

    def test_une_adhesion_payee_par_cawl_est_active_et_encaissee(self, cawl, tenant):
        """Adhésion prise par le formulaire (sans panier), payée chez CAWL, retour
        navigateur : adhésion active, vente REGLEE avec un règlement CAWL de 15 €.
        / Membership through the form, paid at CAWL, browser return: active, settled."""
        from django_tenants.utils import tenant_context
        from fabriques_panier import client_connecte, creer_adhesion, creer_utilisateur, taches_celery_enregistrees
        from test_caracterisation_en_ligne import adherer_sans_panier
        from BaseBillet.models import Membership, PaymentMethod
        from BaseBillet.models_vente import Vente

        with tenant_context(tenant):
            with taches_celery_enregistrees():
                acheteur = creer_utilisateur()
                client = client_connecte(acheteur)
                adhesion = creer_adhesion(prix="15.00")
                adherer_sans_panier(client, acheteur, adhesion.tarif)
                membership = Membership.objects.get(user=acheteur, price=adhesion.tarif)
                paiement = membership.stripe_paiement.get()
                assert paiement.cawl_payment.amount == 1500
                membership.refresh_from_db()
                assert membership.payment_method == PaymentMethod.CAWL

                cawl.capturer(paiement)
                client.get(f"/memberships/{paiement.uuid}/stripe_return/")

                membership.refresh_from_db()
                assert membership.is_valid()
                vente = Vente.objects.get(pk=paiement.vente_id)
                assert vente.statut == Vente.Statut.REGLEE
                assert [r.montant for r in reglements(vente, PaymentMethod.CAWL)] == [1500]


class TestComptabiliteCawl:

    def test_le_plan_comptable_par_defaut_a_un_compte_pour_cawl(self, cawl, evenement, tenant):
        """Une vente CAWL réglée ne bloque pas l'export comptable : CW a son compte.
        / A settled CAWL sale does not block the accounting export: CW has an account."""
        from django_tenants.utils import tenant_context
        from laboutik.plan_comptable import (
            ce_qui_manque_pour_exporter, charger_le_plan_comptable_par_defaut, compte_pour_reglement,
        )

        with tenant_context(tenant):
            charger_le_plan_comptable_par_defaut()
            assert compte_pour_reglement("CW", None).numero_de_compte == "517100"
            reservation, paiement = reservation_payee_par_cawl(cawl, evenement, qty=1)
            manques_cawl = [m for m in ce_qui_manque_pour_exporter()
                            if "CW" in m["phrase"] or "CAWL" in m["phrase"]]
            assert manques_cawl == []

    def test_cawl_compte_dans_les_paiements_en_ligne_du_rapport(self):
        from comptabilite.services import CATEGORIES_PAIEMENT_AFFICHAGE
        en_ligne = dict((cle, codes) for cle, _libelle, codes in CATEGORIES_PAIEMENT_AFFICHAGE)["en_ligne"]
        assert "CW" in en_ligne


class TestEnregistrementHorsTransaction:

    def test_le_passage_a_paid_est_enregistre_hors_transaction(self, cawl, evenement, tenant, monkeypatch):
        """Comme le chemin Stripe : le save() qui passe le paiement à PAID n'est pas dans
        une transaction (le mail des billets part sans attendre le commit).
        / Like Stripe: the save() that turns the payment PAID is outside a transaction."""
        from django.db import connection
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe

        dans_une_transaction = []
        save_d_origine = Paiement_stripe.save

        def save_observe(self, *args, **kwargs):
            if self.status == Paiement_stripe.PAID:
                dans_une_transaction.append(connection.in_atomic_block)
            return save_d_origine(self, *args, **kwargs)

        with tenant_context(tenant):
            reservation, paiement = commander(evenement, qty=1)
            cawl.capturer(paiement)
            monkeypatch.setattr(Paiement_stripe, "save", save_observe)
            paiement.update_checkout_status()
        assert dans_une_transaction and dans_une_transaction[0] is False


def utilisateur_avec_portefeuille(tenant):
    """Une personne avec son portefeuille local (sans appel au Fedow).
    / A person with a local wallet (no Fedow call)."""
    from fabriques_panier import creer_utilisateur
    from AuthBillet.models import Wallet
    personne = creer_utilisateur()
    personne.wallet = Wallet.objects.create(origin=tenant)
    personne.save(update_fields=["wallet"])
    return personne


class TestRechargeEnLigneCawl:

    def test_la_recharge_credite_la_monnaie_du_lieu_une_seule_fois(self, cawl, tenant):
        """Recharge de 12,50 € payée chez CAWL : 1250 centimes de la monnaie LOCALE du lieu
        (celle de son produit « Recharge euros »), une seule transaction même rejouée ;
        vente REGLEE au moyen CAWL, article de recharge hors chiffre d'affaires.
        / 12.50 € top-up: 1250 cents of the venue's LOCAL currency, credited once."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle, Paiement_stripe, PaymentMethod
        from BaseBillet.models_vente import Vente
        from fedow_core.models import Asset, Transaction
        from fedow_core.services import WalletService
        from kiosk.credit import trouver_le_produit_de_recharge_de_la_borne
        from PaiementCawl.recharges import creer_la_recharge_en_ligne, crediter_la_recharge

        with tenant_context(tenant):
            produit, _tarif = trouver_le_produit_de_recharge_de_la_borne()
            monnaie = produit.asset
            assert monnaie.category == Asset.TLF and monnaie.tenant_origin_id == tenant.pk
            personne = utilisateur_avec_portefeuille(tenant)
            solde_avant = WalletService.obtenir_solde(personne.wallet, monnaie)

            adresse = creer_la_recharge_en_ligne(personne, 1250, tenant.get_primary_domain().domain)
            paiement = Paiement_stripe.objects.get(user=personne)
            assert adresse == paiement.cawl_payment.checkout_url
            assert paiement.cawl_payment.amount == 1250
            cawl.capturer(paiement)

            assert paiement.update_checkout_status() == Paiement_stripe.VALID
            paiement.update_checkout_status()
            crediter_la_recharge(paiement)

            recharges = Transaction.objects.filter(checkout_stripe=paiement.uuid, action=Transaction.REFILL)
            assert recharges.count() == 1
            assert recharges.get().receiver_id == personne.wallet.pk
            assert recharges.get().asset_id == monnaie.pk
            assert WalletService.obtenir_solde(personne.wallet, monnaie) == solde_avant + 1250

            vente = Vente.objects.get(pk=paiement.vente_id)
            assert vente.statut == Vente.Statut.REGLEE
            assert [r.montant for r in reglements(vente, PaymentMethod.CAWL)] == [1250]
            ligne = LigneArticle.objects.get(paiement_stripe=paiement)
            assert ligne.hors_chiffre_affaires and ligne.status == LigneArticle.VALID

    def test_une_recharge_non_capturee_ne_credite_rien(self, cawl, tenant):
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe
        from fedow_core.models import Transaction
        from PaiementCawl.recharges import creer_la_recharge_en_ligne

        with tenant_context(tenant):
            personne = utilisateur_avec_portefeuille(tenant)
            creer_la_recharge_en_ligne(personne, 1000, tenant.get_primary_domain().domain)
            paiement = Paiement_stripe.objects.get(user=personne)
            cawl.capturer(paiement, statut="REJECTED")
            assert paiement.update_checkout_status() == Paiement_stripe.CANCELED
            assert not Transaction.objects.filter(checkout_stripe=paiement.uuid).exists()

    @pytest.mark.parametrize("montant", [0, 99, 50001, 12.5])
    def test_un_montant_hors_bornes_est_refuse(self, cawl, tenant, montant):
        from django_tenants.utils import tenant_context
        from rest_framework import serializers
        from PaiementCawl.recharges import creer_la_recharge_en_ligne

        with tenant_context(tenant):
            personne = utilisateur_avec_portefeuille(tenant)
            with pytest.raises(serializers.ValidationError):
                creer_la_recharge_en_ligne(personne, montant, tenant.get_primary_domain().domain)
            assert cawl.pages == {}

    def test_le_parcours_par_le_compte(self, cawl, tenant):
        """Formulaire du compte → page CAWL → retour navigateur → solde crédité.
        / Account form → CAWL page → browser return → balance credited."""
        from django_tenants.utils import tenant_context
        from fabriques_panier import client_connecte, taches_celery_enregistrees
        from BaseBillet.models import Paiement_stripe
        from fedow_core.services import WalletService
        from kiosk.credit import trouver_le_produit_de_recharge_de_la_borne

        with tenant_context(tenant):
            with taches_celery_enregistrees():
                personne = utilisateur_avec_portefeuille(tenant)
                client = client_connecte(personne)
                monnaie = trouver_le_produit_de_recharge_de_la_borne()[0].asset
                assert client.get("/my_account/refill_wallet/").status_code == 200
                reponse = client.post("/my_account/refill_wallet/", {"montant": "7.50"})
                paiement = Paiement_stripe.objects.get(user=personne)
                assert reponse.status_code == 302 and reponse["Location"] == paiement.cawl_payment.checkout_url
                cawl.capturer(paiement)
                retour = client.get(f"/my_account/{paiement.uuid}/return_refill_wallet/")
                assert retour.status_code == 302
                assert WalletService.obtenir_solde(personne.wallet, monnaie) == 750

    def test_la_monnaie_rechargee_ne_se_depense_que_dans_son_lieu(self, cawl, tenant):
        """La monnaie de la recharge est celle du lieu : un autre lieu ne l'accepte pas
        (hors fédération), le lieu lui-même l'accepte.
        / The top-up currency belongs to the venue: another venue does not accept it."""
        from django_tenants.utils import tenant_context
        from Customers.models import Client
        from fedow_core.models import Federation
        from fedow_core.services import AssetService
        from kiosk.credit import trouver_le_produit_de_recharge_de_la_borne

        with tenant_context(tenant):
            monnaie = trouver_le_produit_de_recharge_de_la_borne()[0].asset
        assert not Federation.objects.filter(assets=monnaie).exists()
        assert monnaie in AssetService.obtenir_assets_accessibles(tenant)
        autre_lieu = Client.objects.exclude(pk=tenant.pk).exclude(schema_name="public").first()
        assert monnaie not in AssetService.obtenir_assets_accessibles(autre_lieu)

    def test_une_monnaie_cloturee_n_est_plus_creditee(self, cawl, tenant):
        """Gala clôturé (monnaie désactivée) : un paiement capturé n'est plus crédité.
        / Closed event (inactive currency): a captured payment is no longer credited."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe
        from fedow_core.models import Asset, Transaction
        from kiosk.credit import trouver_le_produit_de_recharge_de_la_borne
        from PaiementCawl.recharges import creer_la_recharge_en_ligne

        with tenant_context(tenant):
            monnaie = trouver_le_produit_de_recharge_de_la_borne()[0].asset
            personne = utilisateur_avec_portefeuille(tenant)
            creer_la_recharge_en_ligne(personne, 1000, tenant.get_primary_domain().domain)
            paiement = Paiement_stripe.objects.get(user=personne)
            cawl.capturer(paiement)
            Asset.objects.filter(pk=monnaie.pk).update(active=False)
            try:
                paiement.update_checkout_status()
                assert not Transaction.objects.filter(checkout_stripe=paiement.uuid).exists()
            finally:
                Asset.objects.filter(pk=monnaie.pk).update(active=True)
