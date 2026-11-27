"""Happy hour LaBoutik : plage horaire, bascules et contrôle serveur des totaux.

Le module est chargé avec des collaborateurs isolés (configuration, prix happy hour) :
pas de serveur LaBoutik, de base de données ni de réseau. Le branchement dans la vue
et le validateur natifs est vérifié par lecture du code source.
"""
import importlib.util
import sys
import types
import unittest
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "Laboutik"
HAS_DJANGO = all(importlib.util.find_spec(name) for name in ("django", "pytz"))


class FakePrices:
    """Remplace HappyHourPrice.objects : filter(...).values_list(...)."""

    def __init__(self, table):
        self.table = table  # {article_id: (prix, methode_choices)}

    def filter(self, article_id__in, article__methode_choices):
        rows = [(pk, prix) for pk, (prix, methode) in self.table.items()
                if pk in article_id__in and methode == article__methode_choices]
        return SimpleNamespace(values_list=lambda *fields: rows)


@unittest.skipUnless(HAS_DJANGO, "requires Django and pytz")
class HappyHourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from django.conf import settings
        if not settings.configured:
            settings.configure(USE_TZ=True, TIME_ZONE="UTC")
        import pytz
        cls.paris = pytz.timezone("Europe/Paris")

    def setUp(self):
        self.schedule = SimpleNamespace(actif=True, debut=time(22, 30), fin=time(23, 30))
        self.prices = {}
        hh_models = types.ModuleType("happy_hour_laboutik.models")
        hh_models.HappyHour = SimpleNamespace(get_solo=lambda: self.schedule)
        hh_models.HappyHourPrice = SimpleNamespace(objects=FakePrices(self.prices))
        cashless = types.ModuleType("APIcashless.models")
        cashless.Configuration = SimpleNamespace(get_solo=lambda: SimpleNamespace(fuseau_horaire="Europe/Paris"))
        self.modules = {
            "happy_hour_laboutik": types.ModuleType("happy_hour_laboutik"),
            "happy_hour_laboutik.models": hh_models,
            "APIcashless": types.ModuleType("APIcashless"),
            "APIcashless.models": cashless,
        }
        self.saved = {name: sys.modules.get(name) for name in self.modules}
        sys.modules.update(self.modules)
        spec = importlib.util.spec_from_file_location("hh_services", ROOT / "happy_hour_laboutik" / "services.py")
        self.services = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.services)

    def tearDown(self):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def at(self, hour, minute, second=0, day=28):
        return self.paris.localize(datetime(2026, 11, day, hour, minute, second))

    def article(self, pk, prix, methode="VT", hh=None):
        if hh is not None:
            self.prices[pk] = (Decimal(hh), methode)
        return SimpleNamespace(pk=pk, prix=Decimal(prix), methode_choices=methode)

    # --- plage horaire ---------------------------------------------------------

    def test_window_22h30_23h30_paris(self):
        state = self.services.state
        self.assertFalse(state(self.at(22, 29, 59))["active"])
        self.assertTrue(state(self.at(22, 30))["active"])
        self.assertTrue(state(self.at(23, 29, 59))["active"])
        self.assertFalse(state(self.at(23, 30))["active"])
        self.assertFalse(state(self.at(12, 0))["active"])

    def test_countdown_points_to_next_change(self):
        self.assertEqual(self.services.state(self.at(22, 0))["seconds_until_change"], 30 * 60 + 1)
        self.assertEqual(self.services.state(self.at(23, 0))["seconds_until_change"], 30 * 60 + 1)
        # Après la fin : prochain début le lendemain à 22h30.
        self.assertEqual(self.services.state(self.at(23, 45))["seconds_until_change"], (22 * 60 + 45) * 60 + 1)

    def test_window_crossing_midnight(self):
        self.schedule.debut, self.schedule.fin = time(23, 0), time(1, 0)
        self.assertTrue(self.services.state(self.at(23, 30))["active"])
        self.assertTrue(self.services.state(self.at(0, 30, day=29))["active"])
        self.assertFalse(self.services.state(self.at(1, 0, day=29))["active"])
        self.assertFalse(self.services.state(self.at(22, 59))["active"])

    def test_disabled_or_empty_window_is_never_active(self):
        self.schedule.actif = False
        self.assertEqual(self.services.state(self.at(23, 0)),
                         {"active": False, "seconds_until_change": None, "near_boundary": False})
        self.schedule.actif, self.schedule.fin = True, time(22, 30)
        self.assertFalse(self.services.state(self.at(22, 30))["active"])

    def test_near_boundary_is_five_minutes_each_side(self):
        state = self.services.state
        self.assertTrue(state(self.at(22, 26))["near_boundary"])
        self.assertTrue(state(self.at(22, 34))["near_boundary"])
        self.assertFalse(state(self.at(22, 40))["near_boundary"])
        self.assertTrue(state(self.at(23, 34))["near_boundary"])
        self.assertFalse(state(self.at(21, 0))["near_boundary"])

    # --- prix envoyés aux caisses ---------------------------------------------

    def payload(self):
        return [{"id": "pv1", "articles": [
            {"id": "pinte", "prix": Decimal("7.50")},
            {"id": "eau", "prix": Decimal("1.00")},
            {"id": "recharge", "prix": Decimal("10.00")},
        ]}]

    def test_payload_gets_happy_prices_only_during_window(self):
        self.prices.update({"pinte": (Decimal("5.50"), "VT"), "recharge": (Decimal("1.00"), "RE")})
        data = self.payload()
        info = self.services.apply_to_payload(data, self.at(22, 45))
        articles = {a["id"]: a for a in data[0]["articles"]}
        self.assertTrue(info["active"])
        self.assertEqual(articles["pinte"]["prix"], "5.50")
        self.assertEqual(articles["pinte"]["prix_normal"], Decimal("7.50"))
        self.assertEqual(articles["eau"]["prix"], Decimal("1.00"))       # champ vide : prix normal
        self.assertEqual(articles["recharge"]["prix"], Decimal("10.00"))  # jamais hors vente
        self.assertEqual(data[0]["happy_hour"], info)

        data = self.payload()
        self.services.apply_to_payload(data, self.at(21, 0))
        self.assertEqual(data[0]["articles"][0]["prix"], Decimal("7.50"))
        self.assertFalse(data[0]["happy_hour"]["active"])

    # --- contrôle serveur des totaux -------------------------------------------

    def lines(self):
        return [{"pk": self.article("pinte", "7.50", hh="5.50"), "qty": Decimal(2)},
                {"pk": self.article("eau", "1.00"), "qty": Decimal(1)}]

    def test_outside_window_native_prices_only(self):
        lines = self.lines()
        self.assertEqual(self.services.resolve_prices(lines, Decimal("16.00"), self.at(21, 0)), Decimal("16.00"))
        with self.assertRaises(ValueError):
            self.services.resolve_prices(self.lines(), Decimal("12.00"), self.at(21, 0))

    def test_inside_window_charges_happy_price(self):
        lines = self.lines()
        self.assertEqual(self.services.resolve_prices(lines, Decimal("12.00"), self.at(23, 0)), Decimal("12.00"))
        self.assertEqual(lines[0]["pk"].prix, Decimal("5.50"))  # prix enregistré dans la vente
        self.assertEqual(lines[1]["pk"].prix, Decimal("1.00"))
        with self.assertRaises(ValueError):
            self.services.resolve_prices(self.lines(), Decimal("16.00"), self.at(23, 0))

    def test_stale_terminal_accepted_near_boundary_with_displayed_price(self):
        # Caisse encore à l'ancien prix juste après 22h30 : on débite le prix affiché.
        lines = self.lines()
        self.assertEqual(self.services.resolve_prices(lines, Decimal("16.00"), self.at(22, 32)), Decimal("16.00"))
        self.assertEqual(lines[0]["pk"].prix, Decimal("7.50"))
        # Caisse encore au prix happy hour juste après 23h30.
        lines = self.lines()
        self.assertEqual(self.services.resolve_prices(lines, Decimal("12.00"), self.at(23, 33)), Decimal("12.00"))
        self.assertEqual(lines[0]["pk"].prix, Decimal("5.50"))

    def test_no_total_uses_current_prices(self):
        lines = self.lines()
        self.assertEqual(self.services.resolve_prices(lines, None, self.at(23, 0)), Decimal("12.00"))

    def test_negative_deposit_return_keeps_native_absolute_comparison(self):
        lines = [{"pk": self.article("retour", "-1.00", methode="CR"), "qty": Decimal(2)}]
        self.assertEqual(self.services.resolve_prices(lines, Decimal("2.00"), self.at(23, 0)), Decimal("-2.00"))


class HappyHourWiringTests(unittest.TestCase):
    def test_native_view_and_validator_delegate_to_the_module(self):
        views = (ROOT / "views.py").read_text()
        validators = (ROOT / "validators.py").read_text()
        self.assertIn("data['happy_hour'] = apply_to_payload(data['data'])", views)
        self.assertIn("total_temp = resolve_prices(value, total_sended if total_sended else None)", validators)

    def test_image_ships_app_migration_template_and_settings(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        for name in ("apps.py", "models.py", "admin.py", "services.py", "migrations/0001_initial.py"):
            self.assertIn(f"deploy/Laboutik/happy_hour_laboutik/{name} /DjangoFiles/happy_hour_laboutik/{name}", dockerfile)
        self.assertIn("source_templates/accueil.html /DjangoFiles/webview/templates/accueil.html", dockerfile)
        self.assertIn("'happy_hour_laboutik',", (ROOT / "settings.py").read_text())

    def test_terminal_script_refreshes_only_when_idle(self):
        template = (ROOT / "source_templates" / "accueil.html").read_text()
        self.assertTrue(template.startswith('{% extends "modele00.html" %}'))
        for needle in ("#popup-cashless", "data-total", "valider_carte_maitresse", "pv_uuid_courant"):
            self.assertIn(needle, template)


if __name__ == "__main__":
    unittest.main()
