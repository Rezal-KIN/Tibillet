"""Exercise card lookup/registration paths with the real source functions.

HTTP, ORM and authentication are instrumented. No service or payment is called.
"""

import ast
import functools
import importlib.util
import json
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1] / "Laboutik"


@functools.lru_cache(maxsize=None)
def source_text(filename):
    if filename != "fedow_api.py":
        return (ROOT / filename).read_text()
    # This file now belongs to the pinned image. Reuse the existing source
    # loader, including its archive SHA-256 check, rather than keeping a copy.
    spec = importlib.util.spec_from_file_location("card_test_source_offer", ROOT.parent / "tools/build-source-offer.py")
    offer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(offer)
    catalog = json.loads((ROOT.parent / "source/image-sources.json").read_text())
    files = offer.upstream_source(catalog["laboutik"], ROOT.parents[1] / ".context/source-cache")
    return files["fedow_connect/fedow_api.py"][0].decode()


class CardRejected(Exception):
    pass


def source_function(filename, name, scope, class_name=None):
    tree = ast.parse(source_text(filename))
    parent = tree if class_name is None else next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    node = next(node for node in parent.body if isinstance(node, ast.FunctionDef) and node.name == name)
    node.decorator_list = []
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, node], type_ignores=[]))
    exec(compile(module, filename, "exec"), scope)
    return scope[name]


def response(code, text="test response"):
    return types.SimpleNamespace(status_code=code, content=text.encode(), text=text, json=lambda: {})


class CardRegistrationTests(unittest.TestCase):
    def prepare(self, lookup, creation=None, valid_payload=True):
        self.card = types.SimpleNamespace(uuid_qrcode="existing-card-uuid", number="printed", save=Mock())
        self.cards = Mock()
        self.cards.get_or_create.return_value = (self.card, False)
        self.cards.get.return_value = self.card
        self.get = Mock(side_effect=lookup)
        self.post = Mock(side_effect=creation or [response(201)])
        payload = {"wallet": {"tokens": []}, "is_wallet_ephemere": True}
        validator = types.SimpleNamespace(
            is_valid=lambda: valid_payload, validated_data=payload, errors={"card": "invalid"},
        )
        scope = {
            "_get": self.get, "_post": self.post, "cache": Mock(), "logger": Mock(),
            "CardValidator": lambda **kwargs: validator,
            "CardSerializer": lambda cards, **kwargs: types.SimpleNamespace(data=[cards[0].uuid_qrcode]),
        }
        retrieve = source_function("fedow_api.py", "retrieve", scope, "NFCCard")
        create = source_function("fedow_api.py", "create", scope, "NFCCard")
        self.nfc = types.SimpleNamespace(config=object())
        self.nfc.retrieve = Mock(side_effect=lambda tag: retrieve(self.nfc, tag))
        self.nfc.create = Mock(side_effect=lambda cards: create(self.nfc, cards))
        self.scope = {
            "FedowAPI": lambda: types.SimpleNamespace(NFCcard=self.nfc),
            "CarteCashless": types.SimpleNamespace(objects=self.cards), "logger": Mock(),
            "serializers": types.SimpleNamespace(ValidationError=CardRejected), "_": lambda value: value,
            "CarteCashlessSerializer": lambda card: types.SimpleNamespace(data={}),
            "render": lambda request, template, data: data,
            "Configuration": types.SimpleNamespace(get_solo=lambda: types.SimpleNamespace(
                verifier_adhesion_paiement_nfc=False,
            )),
        }

    def run_entry(self, entry):
        if entry == "validator":
            fn = source_function("validators.py", "validate_tag_id", self.scope, "DataAchatDepuisClientValidator")
            obj = types.SimpleNamespace(config=types.SimpleNamespace(can_fedow=lambda: True))
            return fn(obj, "aabbccdd")
        fn = source_function("views.py", "check_carte", self.scope)
        return fn(types.SimpleNamespace(method="POST", data={"tag_id_client": "aabbccdd"}))

    def assert_rejected(self, entry):
        if entry == "validator":
            with self.assertRaises(CardRejected):
                self.run_entry(entry)
        else:
            result = self.run_entry(entry)
            self.assertIn("Fedow", result["error_msg"])
            self.assertNotIn("serializer_from_fedow", result)

    def test_known_card_is_read_without_registration(self):
        for entry in ("validator", "scan"):
            with self.subTest(entry=entry):
                self.prepare([response(200)])
                self.run_entry(entry)
                self.nfc.create.assert_not_called()
                self.cards.get_or_create.assert_not_called()
                self.card.save.assert_not_called()

    def test_only_real_404_registers_then_requires_successful_reread(self):
        for entry in ("validator", "scan"):
            for create_code in (201, 409):
                with self.subTest(entry=entry, create_code=create_code):
                    self.prepare([response(404), response(200)], [response(create_code)])
                    self.run_entry(entry)
                    self.cards.get_or_create.assert_called_once()
                    self.assertEqual(self.cards.get_or_create.call_args.kwargs["tag_id"], "AABBCCDD")
                    self.nfc.create.assert_called_once_with([self.card])
                    self.assertEqual(self.nfc.retrieve.call_count, 2)
                    self.assertEqual(self.post.call_args.args[2], ["existing-card-uuid"])
                    self.card.save.assert_not_called()

    def test_auth_gateway_server_and_transport_failures_never_register(self):
        for entry in ("validator", "scan"):
            for failure in (response(403), response(502), response(500),
                            TimeoutError("read timeout"), ConnectionError("network down"),
                            ValueError("signature/payload invalid")):
                with self.subTest(entry=entry, failure=repr(failure)):
                    self.prepare([failure])
                    self.assert_rejected(entry)
                    self.cards.get_or_create.assert_not_called()
                    self.cards.get.assert_not_called()
                    self.nfc.create.assert_not_called()
                    self.post.assert_not_called()

    def test_new_card_uses_generated_identity(self):
        for entry in ("validator", "scan"):
            with self.subTest(entry=entry):
                self.prepare([response(404), response(200)])
                def new_card(**kwargs):
                    self.card.uuid_qrcode = kwargs["defaults"]["uuid_qrcode"]
                    self.card.number = kwargs["defaults"]["number"]
                    return self.card, True
                self.cards.get_or_create.side_effect = new_card
                self.run_entry(entry)
                self.assertEqual(self.card.number, "AABBCCDD")
                self.assertEqual(self.post.call_args.args[2], [self.card.uuid_qrcode])
                self.assertEqual(self.get.call_count, 2)

    def test_invalid_fedow_payload_never_registers(self):
        for entry in ("validator", "scan"):
            with self.subTest(entry=entry):
                self.prepare([response(200)], valid_payload=False)
                self.assert_rejected(entry)
                self.nfc.create.assert_not_called()
                self.cards.get_or_create.assert_not_called()

    def test_failed_creation_or_reread_does_not_report_success(self):
        for entry in ("validator", "scan"):
            for lookups, creations in (
                ([response(404)], [response(500)]),
                ([response(404)], [TimeoutError("registration response lost")]),
                ([response(404), response(404)], [response(409)]),
                ([response(404), response(502)], [response(201)]),
            ):
                with self.subTest(entry=entry, lookup=lookups, creation=creations):
                    self.prepare(lookups, creations)
                    self.assert_rejected(entry)
                    self.nfc.create.assert_called_once()

    def test_retry_reuses_local_identity_after_lost_creation_response(self):
        for entry in ("validator", "scan"):
            with self.subTest(entry=entry):
                self.prepare([response(404), response(404), response(200)],
                             [TimeoutError("response lost"), response(409)])
                self.assert_rejected(entry)
                self.run_entry(entry)
                self.assertEqual(self.post.call_count, 2)
                for call in self.post.call_args_list:
                    self.assertEqual(call.args[2], ["existing-card-uuid"])
                self.card.save.assert_not_called()

    def test_native_duplicate_tag_response_still_requires_successful_reread(self):
        for entry in ("validator", "scan"):
            with self.subTest(entry=entry):
                self.prepare([response(404), response(200)],
                             [response(400, "first_tag_id already exists")])
                self.run_entry(entry)
                self.assertEqual(self.nfc.retrieve.call_count, 2)
                self.nfc.create.assert_called_once_with([self.card])


class NetworkTimeoutTests(unittest.TestCase):
    def test_get_and_post_keep_upstream_network_deadlines(self):
        for method in ("_get", "_post"):
            with self.subTest(method=method):
                session = Mock()
                scope = {
                    "requests": types.SimpleNamespace(Session=lambda: session), "json": json,
                    "settings": types.SimpleNamespace(DEBUG=False),
                    "sign_message": lambda *args: b"signature", "verify_signature": lambda *args: True,
                    "data_to_b64": lambda data: b"data",
                }
                fn = source_function("fedow_api.py", method, scope)
                conf = types.SimpleNamespace(fedow_domain="test.invalid", fedow_place_admin_apikey="test",
                                             get_private_key=lambda: None, get_public_key=lambda: None)
                if method == "_get":
                    fn(conf, ["card", "AABBCCDD"])
                else:
                    fn(conf, "card", [])
                self.assertEqual(getattr(session, method[1:]).call_args.kwargs["timeout"], (3, 5))


if __name__ == "__main__":
    unittest.main()
