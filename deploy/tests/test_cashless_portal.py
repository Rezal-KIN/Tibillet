"""Le portail réutilise le compte du lieu sans ouvrir de redirection libre.
/ The portal reuses venue accounts and never accepts arbitrary return URLs.
"""
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from seo.cashless_portal import portal_space
from seo.context_processors import root_portal
from seo.views import landing


@override_settings(GALA_CASHLESS_PORTAL=True, GALA_CASHLESS_TENANT_SCHEMA="lespass",
                   ALLOWED_HOSTS=["portal.test", "venue.test"], STATIC_URL="/static/")
class CashlessPortalTests(SimpleTestCase):
    def request(self, path="/espace/", schema="public", authenticated=False):
        request = RequestFactory().get(path, HTTP_HOST="portal.test", secure=True)
        request.tenant = SimpleNamespace(schema_name=schema)
        request.user = SimpleNamespace(is_authenticated=authenticated)
        return request

    def test_home_does_not_use_events_or_promote_software_features(self):
        request = self.request("/")
        templates = [{"BACKEND": "django.template.backends.django.DjangoTemplates",
                      "DIRS": [str(settings.BASE_DIR / "seo/templates")], "APP_DIRS": False,
                      "OPTIONS": {"context_processors": ["seo.context_processors.root_portal",
                                                         "django.template.context_processors.request"]}}]
        with override_settings(TEMPLATES=templates), \
                patch("seo.views.get_seo_cache", side_effect=AssertionError("No event aggregation")):
            response = landing(request)
        self.assertContains(response, "Votre carte.")
        self.assertContains(response, 'href="/explorer/"')
        self.assertContains(response, 'href="/espace/"')
        for obsolete_link in ("/features/", "documentation_v3", "codecommun.tibillet.coop/contrib/"):
            self.assertNotContains(response, obsolete_link)
        self.assertNotContains(response, 'data-testid="features-section"')
        self.assertNotContains(response, 'data-testid="top-events"')

    def test_disabled_branding_keeps_the_native_base(self):
        with override_settings(GALA_CASHLESS_PORTAL=False):
            self.assertEqual(root_portal(self.request())["root_base_template"], "seo/base_default.html")
            with self.assertRaises(Http404):
                portal_space(self.request())

    def test_root_opens_the_collective_account_instead_of_a_fixed_venue(self):
        with patch('seo.portal.views.CollectiveViewSet.as_view', return_value=lambda request: HttpResponse('Collectif')):
            response = portal_space(self.request())
        self.assertContains(response, 'Collectif')

    def test_anonymous_user_gets_native_login_with_a_signed_relative_destination(self):
        response = portal_space(self.request("/espace/?section=solde", schema="lespass"))
        url = urlsplit(response.url)
        self.assertEqual(url.path, "/login/login_fullpage/")
        self.assertEqual(signing.loads(parse_qs(url.query)["next"][0]), "/my_account/balance/")

    def test_authenticated_user_keeps_the_existing_session(self):
        response = portal_space(self.request(schema="lespass", authenticated=True))
        self.assertEqual(response.url, "/my_account/")

    def test_arbitrary_destinations_are_rejected_before_any_venue_lookup(self):
        response = portal_space(self.request("/espace/?section=https://untrusted.test"))
        self.assertEqual(response.status_code, 400)

    def test_post_does_not_create_a_session_or_perform_a_payment(self):
        request = self.request()
        request.method = "POST"
        response = portal_space(request)
        self.assertEqual(response.status_code, 405)
