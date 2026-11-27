"""Historique carte (mode gérant LaBoutik) : accès, erreurs et rendu, sans serveur ni base."""
import importlib.util
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "Laboutik"
APP = ROOT / "card_history_laboutik"
HAS_DEPS = all(importlib.util.find_spec(n) for n in ("django", "rest_framework", "pytz"))

LEDGER = {
    'card': {'tag_id': 'ABCD1234', 'number': 'ABCD1234', 'generation': 2, 'linked_to_account': True,
             'email': 'h***@example.test', 'anonymous_wallet': False},
    'balances': [{'asset': 'Euro', 'category': 'TLF', 'value': 500}, {'asset': 'TiBillets', 'category': 'FED', 'value': 1000}],
    'operations': [
        {'datetime': '2026-11-28T21:35:00+00:00', 'action': 'SAL', 'label': 'Achat', 'amount': 750, 'sign': -1,
         'asset': 'Euro', 'asset_category': 'TLF', 'from': 'Carte', 'to': 'Gala', 'online': False, 'comment': ''},
        {'datetime': '2026-11-28T21:30:00+00:00', 'action': 'REF', 'label': 'Recharge', 'amount': 2000, 'sign': 1,
         'asset': 'TiBillets', 'asset_category': 'FED', 'from': 'Banque', 'to': 'Carte', 'online': True, 'comment': ''},
    ],
    'operations_total': 2, 'truncated': False,
    'online_refills': [{'created_at': '2026-11-28T21:29:00+00:00', 'amount': 2000, 'fee': 20,
                        'status': 'CAPTURED', 'credited': True}],
    'online_refunds': [],
}


@unittest.skipUnless(HAS_DEPS, "requires Django, DRF and pytz")
class CardHistoryViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from django.conf import settings
        cls.stub = tempfile.mkdtemp()
        (Path(cls.stub) / "elements").mkdir()
        (Path(cls.stub) / "elements" / "bouton_return.html").write_text('<div id="popup-retour">RETOUR</div>')
        if not settings.configured:
            settings.configure(
                USE_TZ=True, TIME_ZONE="UTC", SECRET_KEY="qa", ROOT_URLCONF=__name__,
                INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "rest_framework"],
                TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates",
                            "DIRS": [str(APP / "templates"), cls.stub]}],
                REST_FRAMEWORK={"DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
                                "DEFAULT_AUTHENTICATION_CLASSES": [], "UNAUTHENTICATED_USER": None},
            )
        else:
            settings.TEMPLATES[0]["DIRS"] += [str(APP / "templates"), cls.stub]
        import django
        django.setup()

    def setUp(self):
        cashless = types.ModuleType("APIcashless.models")
        cashless.Configuration = types.SimpleNamespace(
            get_solo=lambda: types.SimpleNamespace(fuseau_horaire="Europe/Paris"))
        # Seuls les modules simulés sont restaurés : patch.dict(sys.modules) retirerait aussi
        # les modules importés pendant le test (requests…) et casserait les tests suivants.
        fakes = {"APIcashless": types.ModuleType("APIcashless"), "APIcashless.models": cashless}
        saved = {name: sys.modules.get(name) for name in fakes}
        sys.modules.update(fakes)

        def restore():
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
        self.addCleanup(restore)
        spec = importlib.util.spec_from_file_location("card_history_views", APP / "views.py")
        self.views = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.views)
        self.views.manager_allowed = lambda tag: tag == "CAFE0001"
        self.views.fedow_history = lambda tag: LEDGER if tag == "ABCD1234" else None
        self.views.till_sales = lambda tag: [{
            'datetime': self.views.local(datetime(2026, 11, 28, 21, 35, tzinfo=timezone.utc)), 'article': 'Kohlneim 50cl',
            'qty': Decimal('1'), 'total': Decimal('7.50'), 'payment': 'Cashless', 'pos': 'Bières ATS', 'by': 'Barman'}]

    def call(self, tag="ABCD1234", cm="CAFE0001", terminal=True):
        import copy
        from rest_framework.test import APIRequestFactory, force_authenticate
        self.views.fedow_history = (lambda t: copy.deepcopy(LEDGER) if t == "ABCD1234" else None)
        request = APIRequestFactory().post("/gala/card_history/", {"tag_id_client": tag, "tag_id_cm": cm}, format="multipart")
        user = types.SimpleNamespace(is_authenticated=True, **({"appareil": object()} if terminal else {}))
        force_authenticate(request, user=user)
        response = self.views.card_history(request)
        return response.status_code, response.content.decode()

    def test_manager_sees_full_history_in_local_time(self):
        status, html = self.call()
        self.assertEqual(status, 200)
        for needle in ("Historique carte ABCD1234", "15.00 €", "Associée à un compte", "h***@example.test",
                       "Recharge", "en ligne", "+20.00 €", "−7.50 €", "+ 0.20 € de frais", "Payée et créditée",
                       "Kohlneim 50cl", "Bières ATS", "28/11 22:35:00", 'id="popup-cashless"', "RETOUR"):
            self.assertIn(needle, html)

    def test_refused_without_manager_card_or_terminal(self):
        status, html = self.call(cm="00000000")
        self.assertEqual(status, 403)
        self.assertIn("réservé au mode gérant", html)
        self.assertEqual(self.call(terminal=False)[0], 403)

    def test_unreadable_and_unknown_cards(self):
        self.assertIn("Carte illisible", self.call(tag="erreur")[1])
        self.assertIn("Carte inconnue", self.call(tag="FFFFFFFF")[1])

    def test_fedow_unreachable(self):
        def boom(tag):
            raise ConnectionError()
        self.views.fedow_history = boom
        from rest_framework.test import APIRequestFactory, force_authenticate
        request = APIRequestFactory().post("/gala/card_history/", {"tag_id_client": "ABCD1234", "tag_id_cm": "CAFE0001"})
        force_authenticate(request, user=types.SimpleNamespace(is_authenticated=True, appareil=object()))
        self.assertIn("Impossible de joindre Fedow", self.views.card_history(request).content.decode())


class CardHistoryWiringTests(unittest.TestCase):
    def test_app_config_route_and_image(self):
        self.assertIn("default_app_config = 'card_history_laboutik.apps.CardHistoryLaboutikConfig'",
                      (APP / "__init__.py").read_text())
        self.assertIn("path('gala/card_history/'", (APP / "apps.py").read_text())
        dockerfile = (ROOT / "Dockerfile").read_text()
        for name in ("__init__.py", "apps.py", "views.py", "templates/card_history_laboutik/popup_card_history.html"):
            self.assertIn(f"deploy/Laboutik/card_history_laboutik/{name} /DjangoFiles/card_history_laboutik/{name}", dockerfile)
        self.assertIn("'card_history_laboutik',", (ROOT / "settings.py").read_text())

    def test_menu_entry_is_manager_only_and_posts_primary_card(self):
        template = (ROOT / "source_templates" / "accueil.html").read_text()
        for needle in ("glob.passageModeGerant !== true", "glob.modeGerant !== true", "/gala/card_history/",
                       "tag_id_cm: glob.tagIdCm", "addPluginFunctionsToMenu"):
            self.assertIn(needle, template)

    def test_fedow_route_is_registered_and_shipped(self):
        fedow = Path(__file__).resolve().parents[1] / "Fedow"
        self.assertIn('path("card_history/<str:pk>/"', (fedow / "cawl_fedow" / "urls.py").read_text())
        self.assertIn("deploy/Fedow/cawl_fedow/history.py", (fedow / "Dockerfile").read_text())


urlpatterns = []

if __name__ == "__main__":
    unittest.main()
