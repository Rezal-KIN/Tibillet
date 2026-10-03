"""Exercise the real price validator and terminal response with isolated collaborators.

These tests need no LaBoutik server, database, or network. HTTP/authentication and
ORM collaborators are instrumented; this is not a full cashless integration test.
"""

import ast
import os
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1] / "Laboutik"


class PriceRejected(Exception):
    pass


def source_function(filename, name, scope, class_name=None):
    source = ROOT / filename
    tree = ast.parse(source.read_text())
    parent = tree if class_name is None else next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    node = next(node for node in parent.body if isinstance(node, ast.FunctionDef) and node.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), scope)
    return scope[name]


class ArticlePricesTests(unittest.TestCase):
    def setUp(self):
        self.scope = {
            "Decimal": Decimal,
            "os": os,
            "logger": Mock(),
            "capture_message": Mock(),
            "_": lambda value: value,
            "serializers": types.SimpleNamespace(ValidationError=PriceRejected),
        }
        source_function("validators.py", "dround", self.scope)
        self.validate = source_function(
            "validators.py", "validate_articles", self.scope,
            "DataAchatDepuisClientValidator",
        )

    def validate_total(self, total, rows):
        obj = types.SimpleNamespace(initial_data={"total": total, "pk_pdv": "caisse"})
        # Old server environment values must have no effect after removing C.
        with patch.dict(os.environ, HAPPY_HOUR_START="00:00", HAPPY_HOUR_END="23:59",
                        HAPPY_HOUR_PRICE_FILE="/old/happy_hour_prices.json"):
            return self.validate(obj, rows)

    def test_normal_total_uses_stored_prices_and_quantities(self):
        beer = types.SimpleNamespace(prix=Decimal("4.00"))
        water = types.SimpleNamespace(prix=Decimal("1.00"))
        rows = [{"pk": beer, "qty": 2}, {"pk": water, "qty": 3}]
        self.assertIs(self.validate_total("11.00", rows), rows)
        self.assertEqual(beer.prix, Decimal("4.00"))

    def test_old_discounted_total_is_rejected_without_changing_article_price(self):
        beer = types.SimpleNamespace(prix=Decimal("4.00"))
        with self.assertRaises(PriceRejected):
            self.validate_total("3.00", [{"pk": beer, "qty": 1}])
        self.assertEqual(beer.prix, Decimal("4.00"))

    def test_incorrect_total_is_rejected(self):
        beer = types.SimpleNamespace(prix=Decimal("4.00"))
        with self.assertRaises(PriceRejected):
            self.validate_total("9.00", [{"pk": beer, "qty": 2}])

    def test_deposit_return_keeps_existing_negative_quantity_handling(self):
        deposit = types.SimpleNamespace(prix=Decimal("1.00"))
        rows = [{"pk": deposit, "qty": -2}]
        self.assertIs(self.validate_total("-2.00", rows), rows)

    def test_terminal_receives_normal_prices_on_primary_card_scan(self):
        payload = [{"name": "PIAN'S", "articles": [{"id": "beer", "name": "Bière", "prix": "4.00"}]}]
        primary = Mock(edit_mode=False)
        primary.carte.membre = types.SimpleNamespace(name="Cashier", id="cashier")
        config = types.SimpleNamespace(currency_code="EUR", monnaie_principale=types.SimpleNamespace(name="Cashless"))
        conf_manager = Mock()
        conf_manager.get.return_value = config
        request = types.SimpleNamespace(
            method="POST", user=types.SimpleNamespace(username="till", appareil=object()),
            POST={"type-action": "valider_carte_maitresse", "tag-id-cm": "abcd"},
        )
        nfc = Mock()
        nfc.retrieve.return_value = {"is_primary": True}
        primary_manager = Mock()
        primary_manager.get.return_value = primary
        article_manager = Mock()
        article_manager.get.return_value = types.SimpleNamespace(pk="fraction")
        terminal_manager = Mock()
        terminal_manager.filter.return_value.exists.return_value = False
        scope = {
            "_enforce_active_terminal_user": Mock(return_value=None),
            "_limit_cash_register_connections": Mock(),
            "settings": types.SimpleNamespace(DEMO=False),
            "Configuration": types.SimpleNamespace(get_solo=lambda: config, objects=conf_manager),
            "logger": Mock(), "FedowAPI": lambda: types.SimpleNamespace(NFCcard=nfc),
            "CarteMaitresse": types.SimpleNamespace(objects=primary_manager),
            "Articles": types.SimpleNamespace(FRACTIONNE="FR", objects=article_manager),
            "Table": types.SimpleNamespace(objects=Mock()),
            "Terminal": types.SimpleNamespace(STRIPE_WISEPOS="SW", objects=terminal_manager),
            "PointDeVenteSerializer": lambda *a, **k: types.SimpleNamespace(data=payload),
            "TableSerializer": lambda *a, **k: types.SimpleNamespace(data=[]),
            "ConfigurationSerializer": lambda *a: types.SimpleNamespace(data={}),
            "Response": lambda data, status: types.SimpleNamespace(data=data, status_code=status),
            "status": types.SimpleNamespace(HTTP_200_OK=200),
        }
        index = source_function("views.py", "index", scope)
        response = index(request)
        self.assertEqual(response.status_code, 200)
        article = response.data["data"][0]["articles"][0]
        self.assertEqual(article["prix"], "4.00")
        self.assertNotIn("happy_hour", article)
        self.assertNotIn("prix_normal", article)


if __name__ == "__main__":
    unittest.main()
