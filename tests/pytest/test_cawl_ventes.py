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
