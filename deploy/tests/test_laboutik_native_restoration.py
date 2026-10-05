"""Native sale/error contracts with instrumented HTTP/ORM, never real payments."""

import json
import types
import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID

import test_laboutik_card_registration as card_tests
from test_laboutik_card_registration import source_function


class Rejected(Exception):
    def __init__(self, detail=None, code=None):
        self.detail, self.code = detail, code
        super().__init__(detail)


class TicketError(Exception):
    pass


class NativeTicketTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.reserve = Mock(side_effect=lambda **kwargs: self.events.append("reserve") or {"identifier": "reservation"})
        self.sales = Mock()
        self.sales.create.side_effect = lambda **kwargs: self.events.append("sale")
        self.scope = {
            "MoyenPaiement": types.SimpleNamespace(CASH="cash", CREDIT_CARD_NOFED="card"),
            "ArticleVendu": types.SimpleNamespace(objects=self.sales),
            "envoyer_reservation_billet": self.reserve, "EnvoiBilletErreur": TicketError,
            "NotAcceptable": Rejected, "_": lambda text: text, "json": json,
        }
        self.sell = source_function("views.py", "methode_BI", self.scope, "Commande")
        self.command = types.SimpleNamespace(
            total_vente_article=Decimal("0"), configuration=types.SimpleNamespace(email="cashier@example.invalid"),
            moyen_paiement=types.SimpleNamespace(categorie="cash", name="Espèce"), carte_db=None,
            point_de_vente=object(), responsable=object(), uuid_commande="command", uuid_paiement="payment",
            table=None, ip_user=None, reponse={},
        )
        self.article = types.SimpleNamespace(prix=Decimal("10"), prix_achat=Decimal("0"), categorie=None)

    def test_ticket_reservation_precedes_local_sale(self):
        self.sell(self.command, self.article, 1)
        self.assertEqual(self.events, ["reserve", "sale"])
        self.assertEqual(self.reserve.call_args.kwargs["email"], "cashier@example.invalid")
        self.assertEqual(self.reserve.call_args.kwargs["payment_method"], "cash")
        metadata = json.loads(self.sales.create.call_args.kwargs["metadata"])
        self.assertEqual(metadata["lespass_reservation"], "reservation")

    def test_ticket_api_failure_records_no_local_sale(self):
        self.reserve.side_effect = TicketError("Lespass unavailable")
        with self.assertRaisesRegex(Rejected, "Lespass unavailable"):
            self.sell(self.command, self.article, 1)
        self.sales.create.assert_not_called()

    def test_ticket_unsupported_payment_calls_no_api_or_sale(self):
        self.command.moyen_paiement.categorie = "cashless"
        with self.assertRaises(Rejected):
            self.sell(self.command, self.article, 1)
        self.reserve.assert_not_called()
        self.sales.create.assert_not_called()


class NativeMembershipTests(unittest.TestCase):
    def test_subscription_failure_raises_instead_of_returning_http_code_or_errors(self):
        for code, payload, message in (
            (400, {"primary_card_fisrtTagId": ["invalid"]}, "Carte primaire non valide"),
            (502, {"detail": "gateway"}, "gateway"),
            (201, {}, "invalid transaction"),
        ):
            with self.subTest(code=code):
                response = types.SimpleNamespace(status_code=code, json=lambda: payload)
                scope = {
                    "_post": Mock(return_value=response), "logger": Mock(), "NotAcceptable": Rejected,
                    "UUID": UUID, "localtime": lambda: datetime(2026, 10, 5),
                    "Articles": types.SimpleNamespace(ADHESIONS="AD"),
                    "TransactionValidator": lambda **kwargs: types.SimpleNamespace(
                        is_valid=lambda: False, errors={"detail": "invalid transaction"},
                    ),
                }
                create = source_function("fedow_api.py", "create_sub", scope, "Subscription")
                with self.assertRaisesRegex(Rejected, message) as failure:
                    create(types.SimpleNamespace(config=types.SimpleNamespace(fedow_place_wallet_uuid="place")),
                           wallet="11111111-1111-1111-1111-111111111111", amount=100,
                           article=types.SimpleNamespace(methode_choices="AD", fedow_asset=types.SimpleNamespace(pk="asset")))
                self.assertEqual(failure.exception.code, str(code))

    def test_badge_uses_primary_card_and_native_fallback(self):
        for own_primary in (True, False):
            with self.subTest(own_primary=own_primary):
                cards = Mock()
                cards.filter.return_value.first.return_value = (
                    types.SimpleNamespace(carte=types.SimpleNamespace(tag_id="PRIMARY")) if own_primary else None
                )
                cards.last.return_value = types.SimpleNamespace(carte=types.SimpleNamespace(tag_id="FALLBACK"))
                member = types.SimpleNamespace(CarteCashless_Membre=Mock())
                member.CarteCashless_Membre.first.side_effect = AssertionError("Personal card must not be selected")
                sale = types.SimpleNamespace(
                    pk="sale", responsable=member, carte=types.SimpleNamespace(tag_id="CLIENT"),
                    article=types.SimpleNamespace(fedow_asset=types.SimpleNamespace(pk="asset")),
                    pos=types.SimpleNamespace(id="pos", name="Till"),
                )
                post = Mock(return_value=types.SimpleNamespace(status_code=201, json=lambda: {}))
                scope = {
                    "CarteMaitresse": types.SimpleNamespace(objects=cards), "_post": post, "logger": Mock(),
                    "ArticleVendu": types.SimpleNamespace(objects=Mock()),
                    "TransactionValidator": lambda **kwargs: types.SimpleNamespace(
                        is_valid=lambda: True, validated_data={"hash": "transaction"},
                    ),
                }
                badge = source_function("fedow_api.py", "badge", scope, "NFCCard")
                badge(types.SimpleNamespace(config=object()), article_vendu=sale)
                self.assertEqual(post.call_args.args[2]["primary_card_firstTagId"], "PRIMARY" if own_primary else "FALLBACK")
                member.CarteCashless_Membre.first.assert_not_called()

    def test_scan_uses_actual_membership_validity_when_enabled(self):
        # Reuse the existing card-path instrumentation, without inheriting its
        # test cases or invoking a real ORM or network request.
        harness = card_tests.CardRegistrationTests()
        harness.prepare([card_tests.response(200)])
        harness.card.get_wallet = Mock(return_value=types.SimpleNamespace(uuid="wallet"))
        config = types.SimpleNamespace(verifier_adhesion_paiement_nfc=True, lespass_api_key="test")
        memberships = [{"is_valid": False}, {"is_valid": True}]
        lookup = Mock(return_value=memberships)
        harness.scope.update(
            Configuration=types.SimpleNamespace(get_solo=lambda: config),
            fetch_adhesions=lookup, couleur_adhesion=Mock(return_value="#339448"),
        )
        result = harness.run_entry("scan")
        lookup.assert_called_once_with("wallet", config)
        self.assertTrue(result["lespass_repondu"])
        self.assertEqual(result["adhesions_valides"], [{"is_valid": True}])
        harness.nfc.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
