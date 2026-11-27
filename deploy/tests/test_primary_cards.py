"""Onglet admin « Cartes primaires (NFC) » : lecture des identifiants, chemins natifs, branchements."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "Laboutik"
APP = ROOT / "card_history_laboutik"
HAS_DJANGO = bool(importlib.util.find_spec("django"))


@unittest.skipUnless(HAS_DJANGO, "requires Django")
class CandidateTagTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("primary_cards", APP / "primary_cards.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_web_nfc_serial_number(self):
        # Chrome Android : « 26:c2:66:c5 » → identifiant natif, puis ordre inverse en secours.
        self.assertEqual(self.module.candidates("26:c2:66:c5"), ["26C266C5", "C566C226"])

    def test_keyboard_reader_decimal(self):
        self.assertEqual(self.module.candidates(str(0x26C266C5))[:2], ["26C266C5", "C566C226"])

    def test_garbage_gives_nothing(self):
        self.assertEqual(self.module.candidates("hello"), [])
        self.assertEqual(self.module.candidates(""), [])


class PrimaryCardsWiringTests(unittest.TestCase):
    def test_native_admin_paths_and_guard(self):
        source = (APP / "primary_cards.py").read_text()
        for route in ("adminstaff/cartes-primaires/", "adminstaff/cartes-primaires/carte/",
                      "adminstaff/cartes-primaires/enregistrer/", "adminstaff/cartes-primaires/retirer/"):
            self.assertIn(f"path('{route}', guard(", source)
        self.assertIn("guard = staff_admin_site.admin_view", source)
        # Étapes natives : carte depuis Fedow, membre, CarteMaitresse (signaux natifs → Fedow).
        for native in ("FedowAPI().NFCcard.retrieve(tag)", "Membre.objects.create(", "CarteMaitresse.objects.get_or_create(carte=card)",
                       "primary.points_de_vente.set(points)", "primary.delete()"):
            self.assertIn(native, source)
        self.assertIn("primary_card_urls()", (APP / "apps.py").read_text())

    def test_side_menu_and_image(self):
        self.assertIn("{'url': '/adminstaff/cartes-primaires/', 'label': \"Cartes primaires (NFC)\"}",
                      (ROOT / "settings.py").read_text())
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn("card_history_laboutik/primary_cards.py /DjangoFiles/card_history_laboutik/primary_cards.py", dockerfile)
        self.assertIn("card_history_laboutik/primary_cards.html /DjangoFiles/card_history_laboutik/templates/card_history_laboutik/primary_cards.html", dockerfile)

    def test_page_offers_scan_and_printed_number(self):
        page = (APP / "templates" / "card_history_laboutik" / "primary_cards.html").read_text()
        self.assertTrue(page.startswith('{% extends "admin/base_site.html" %}'))
        for needle in ("'NDEFReader' in window", "Scanner la carte", "Numéro imprimé sur la carte",
                       "mode: mode", "'numero'", "X-CSRFToken"):
            self.assertIn(needle, page)

    def test_fedow_number_route(self):
        fedow = Path(__file__).resolve().parents[1] / "Fedow" / "cawl_fedow"
        self.assertIn('path("card_history/number/<str:number>/"', (fedow / "urls.py").read_text())


if __name__ == "__main__":
    unittest.main()
