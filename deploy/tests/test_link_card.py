"""« Associer ma carte » depuis Mon compte : liaison native par numéro imprimé."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class LinkCardContractTests(unittest.TestCase):
    def view_source(self):
        tree = ast.parse((ROOT / "BaseBillet/views.py").read_text())
        account = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MyAccount")
        node = next(n for n in account.body if isinstance(n, ast.FunctionDef) and n.name == "link_card")
        return ast.get_source_segment((ROOT / "BaseBillet/views.py").read_text(), node)

    def test_uses_native_fedow_link_and_guards(self):
        source = self.view_source()
        self.assertIn("fedow.NFCcard.linkwallet_card_number(user=request.user, card_number=number)", source)
        self.assertIn("if not request.user.email_valid", source)
        self.assertIn("if request.method == 'GET' or context['has_card']", source)  # jamais une 2e carte
        self.assertIn(r"re.fullmatch(r'[A-Z0-9]{8}', number)", source)

    def test_account_page_offers_the_button_only_without_card(self):
        index = (ROOT / "BaseBillet/templates/reunion/views/account/index.html").read_text()
        self.assertIn('/my_account/balance_summary/?part=link', index)
        partial = (ROOT / "BaseBillet/templates/reunion/partials/account/balance_summary.html").read_text()
        self.assertIn("{% if has_card is False %}", partial)
        self.assertIn('href="/my_account/link_card/"', partial)
        # Encadré blanc : un bouton clair y serait invisible (vu en production le 27/11).
        self.assertNotIn("btn-outline", partial)
        # Même style que « Recharger ma carte » (bleu plein, texte blanc lisible).
        self.assertIn('class="btn btn-primary btn-lg w-100"', partial)


if __name__ == "__main__":
    unittest.main()
