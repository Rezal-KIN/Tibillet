"""The browser entry asks for login, then delegates access checks to the register."""
import os
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from django.test import RequestFactory
from django.core import signing
from django.urls import reverse

from laboutik.entry import ouvrir_caisse


def requete(authentifie):
    request = RequestFactory().get(
        "/laboutik/ouvrir/",
        HTTP_HOST=os.environ.get("TEST_TENANT_HOST", "lespass.tibillet.localhost"),
    )
    request.user = SimpleNamespace(is_authenticated=authentifie)
    return request


def test_entree_anonyme_demande_la_connexion_avec_retour():
    response = ouvrir_caisse(requete(False))
    target = urlsplit(response.url)
    assert response.status_code == 302
    assert target.path == reverse("login-viewset-login-fullpage")
    query = parse_qs(target.query)
    assert set(query) == {"next"}
    assert signing.loads(query["next"][0]) == "/laboutik/caisse/"


def test_entree_connectee_rejoint_la_caisse():
    response = ouvrir_caisse(requete(True))
    assert response.status_code == 302
    assert response.url == "/laboutik/caisse/"
