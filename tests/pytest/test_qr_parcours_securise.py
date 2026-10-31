"""
Parcours QR de la carte cashless : le QR imprimé ne connecte personne.
/ Cashless card QR journey: the printed QR signs nobody in.

LOCALISATION : tests/pytest/test_qr_parcours_securise.py
Vue testée : BaseBillet/views.py ScanQrCode. Fedow est simulé, aucun mail ne part.
"""

import uuid
from unittest import mock

import pytest
from django.core import signing
from django.core.cache import cache
from django.test import Client as DjangoClient
from django.template.loader import render_to_string
from django_tenants.utils import tenant_context

from Customers.models import Client

HOTE = "lespass.tibillet.localhost"


@pytest.fixture
def tenant(db):
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def navigateur():
    return DjangoClient(HTTP_HOST=HOTE)


def _personne(tenant, nom):
    from AuthBillet.models import TibilletUser, Wallet

    with tenant_context(tenant):
        wallet = Wallet.objects.create(origin=tenant)
        email = f"{nom}-{uuid.uuid4().hex[:8]}@mock.test"
        return TibilletUser.objects.create(email=email, username=email, is_active=True, wallet=wallet)


def _fedow(ephemere=True, wallet_uuid=None):
    api = mock.MagicMock()
    api.NFCcard.qr_retrieve.return_value = {
        "origin": {"place": {"lespass_domain": HOTE}},
        "is_wallet_ephemere": ephemere,
        "wallet_uuid": wallet_uuid,
    }
    return api


def _formulaire(qrcode_uuid, email):
    return {"email": email, "emailConfirmation": email, "cgu": True, "qrcode_uuid": str(qrcode_uuid)}


def _est_connecte(navigateur):
    return "_auth_user_id" in navigateur.session


def test_scanner_la_carte_d_un_autre_sans_session_ne_connecte_pas(tenant, navigateur):
    """Le propriétaire reçoit un lien par mail, le visiteur reste anonyme."""
    proprietaire = _personne(tenant, "proprio")
    carte = uuid.uuid4()
    with mock.patch("BaseBillet.views.FedowAPI", return_value=_fedow(False, proprietaire.wallet.uuid)), \
            mock.patch("BaseBillet.views.sender_mail_connect") as mail:
        reponse = navigateur.get(f"/qr/{carte}/")
    assert reponse.status_code == 200
    assert b'data-testid="qr-verifier-mail"' in reponse.content
    assert not _est_connecte(navigateur)
    assert mail.call_args.args[0] == proprietaire.email
    assert signing.loads(mail.call_args.kwargs["next_url"]) == f"/qr/{carte}/"


def test_des_scans_repetes_n_envoient_qu_un_mail(tenant, navigateur):
    proprietaire = _personne(tenant, "repete")
    carte = uuid.uuid4()
    cache.delete(f"qr-lien-connexion:{carte}:{proprietaire.pk}")
    with mock.patch("BaseBillet.views.FedowAPI", return_value=_fedow(False, proprietaire.wallet.uuid)), \
            mock.patch("BaseBillet.views.sender_mail_connect") as mail:
        navigateur.get(f"/qr/{carte}/")
        navigateur.get(f"/qr/{carte}/")
    assert mail.call_count == 1


def test_le_proprietaire_connecte_voit_sa_carte(tenant, navigateur):
    proprietaire = _personne(tenant, "connecte")
    navigateur.force_login(proprietaire)
    with mock.patch("BaseBillet.views.FedowAPI", return_value=_fedow(False, proprietaire.wallet.uuid)):
        reponse = navigateur.get(f"/qr/{uuid.uuid4()}/")
    assert b'data-testid="qr-carte-liee"' in reponse.content


def test_une_autre_personne_connectee_est_refusee(tenant, navigateur):
    proprietaire = _personne(tenant, "proprio2")
    navigateur.force_login(_personne(tenant, "autre"))
    with mock.patch("BaseBillet.views.FedowAPI", return_value=_fedow(False, proprietaire.wallet.uuid)), \
            mock.patch("BaseBillet.views.sender_mail_connect") as mail:
        reponse = navigateur.get(f"/qr/{uuid.uuid4()}/")
    assert reponse.status_code == 403
    mail.assert_not_called()


def test_un_email_connu_ne_lie_rien_et_ne_connecte_pas(tenant, navigateur):
    """Connaître une adresse ne suffit pas : lien par mail d'abord."""
    existant = _personne(tenant, "existant")
    carte = uuid.uuid4()
    api = _fedow()
    with mock.patch("BaseBillet.views.FedowAPI", return_value=api), \
            mock.patch("BaseBillet.views.sender_mail_connect") as mail:
        reponse = navigateur.post("/qr/link/", _formulaire(carte, existant.email))
    assert reponse["HX-Redirect"] == f"/qr/{carte}/verifier-mail/"
    assert not _est_connecte(navigateur)
    assert not api.NFCcard.linkwallet_cardqrcode.called
    assert mail.call_args.args[0] == existant.email


def test_une_carte_inconnue_n_envoie_aucun_mail(tenant, navigateur):
    """Sinon, des uuid inventés inonderaient la boîte d'une adresse connue."""
    existant = _personne(tenant, "inconnue")
    api = _fedow()
    api.NFCcard.qr_retrieve.return_value = None
    with mock.patch("BaseBillet.views.FedowAPI", return_value=api), \
            mock.patch("BaseBillet.views.sender_mail_connect") as mail:
        navigateur.post("/qr/link/", _formulaire(uuid.uuid4(), existant.email))
    mail.assert_not_called()


def test_un_nouvel_email_lie_et_entre_tout_de_suite(tenant, navigateur):
    """Compte neuf : liaison et session immédiates, l'email reste à confirmer."""
    from AuthBillet.models import TibilletUser

    carte = uuid.uuid4()
    email = f"neuf-{uuid.uuid4().hex[:8]}@mock.test"
    api = _fedow()
    api.wallet.get_or_create_wallet.return_value = (mock.MagicMock(), True)
    api.NFCcard.linkwallet_cardqrcode.return_value = {"qrcode_uuid": str(carte), "number_printed": None}
    api.NFCcard.retrieve_card_by_signature.return_value = []
    with mock.patch("BaseBillet.views.FedowAPI", return_value=api), \
            mock.patch("AuthBillet.utils.sender_mail_connect") as mail, \
            mock.patch("QrcodeCashless.services.relier_la_copie_locale_de_la_carte"), \
            mock.patch("QrcodeCashless.services.aligner_les_cartes_locales_sur_fedow"):
        reponse = navigateur.post("/qr/link/", _formulaire(carte, email))
    assert reponse["HX-Redirect"] == f"/qr/{carte}/"
    assert _est_connecte(navigateur)
    assert mail.called
    with tenant_context(tenant):
        user = TibilletUser.objects.get(email=email)
        assert user.is_active is True
        assert user.email_valid is False


def test_scanner_une_carte_vierge_connecte_demande_confirmation(tenant, navigateur):
    """Un simple scan ne lie jamais une carte à un compte : il faut confirmer."""
    navigateur.force_login(_personne(tenant, "confirme"))
    api = _fedow()
    with mock.patch("BaseBillet.views.FedowAPI", return_value=api):
        reponse = navigateur.get(f"/qr/{uuid.uuid4()}/")
    assert b'data-testid="qr-lier-ma-carte"' in reponse.content
    assert not api.NFCcard.linkwallet_cardqrcode.called


def test_le_panneau_cashless_s_affiche():
    html = render_to_string("pages/classic/partials/carte_cashless.html")
    assert 'data-testid="carte-cashless"' in html
