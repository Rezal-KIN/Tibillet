"""API Direct CAWL, avec le SDK officiel Online Payments.

FR : Aucun montant, marchand ou statut n'est déduit du retour navigateur.
EN: Never trust browser-supplied amounts, merchants or payment status.
"""

import hmac
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit
from uuid import UUID


class CawlError(Exception):
    """Erreur publique sans données de carte ni secrets. / Safe public error."""


@dataclass(frozen=True)
class CawlConfiguration:
    merchant_id: str
    api_key_id: str = field(repr=False)
    api_secret: str = field(repr=False)
    webhook_key_id: str = field(repr=False)
    webhook_secret: str = field(repr=False)
    test_mode: bool = True

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]):
        mode = environment.get("CAWL_TEST", "1")
        if mode not in {"0", "1"}:
            raise CawlError("CAWL_TEST doit valoir 0 ou 1.")
        values = {}
        for name, variable in [
            ("merchant_id", "CAWL_MERCHANT_ID"),
            ("api_key_id", "CAWL_API_KEY_ID"),
            ("api_secret", "CAWL_API_SECRET"),
            ("webhook_key_id", "CAWL_WEBHOOK_KEY_ID"),
            ("webhook_secret", "CAWL_WEBHOOK_SECRET"),
        ]:
            value = environment.get(variable, "")
            if not value or value != value.strip():
                raise CawlError(f"Configuration manquante ou invalide : {variable}.")
            values[name] = value
        return cls(**values, test_mode=mode == "1")

    @property
    def endpoint(self):
        if self.test_mode:
            return "https://payment.preprod.cawl-solutions.fr"
        return "https://payment.cawl-solutions.fr"


@dataclass(frozen=True)
class HostedCheckout:
    id: str
    url: str
    return_mac: str = field(repr=False)


@dataclass(frozen=True)
class PaymentSnapshot:
    id: str
    reference: str
    amount: int
    currency: str
    status: str

    @property
    def captured(self):
        # FR : Une autorisation ou une capture demandée ne crédite pas un wallet.
        # EN: Authorisation and capture requests must not credit a wallet.
        return self.status == "CAPTURED"

    @classmethod
    def from_dictionary(cls, payment):
        try:
            output = payment["paymentOutput"]
            money = output["amountOfMoney"]
            amount = money["amount"]
            if type(amount) is not int or amount <= 0:
                raise ValueError
            return cls(
                id=payment["id"],
                reference=output["references"]["merchantReference"],
                amount=amount,
                currency=money["currencyCode"],
                status=payment["status"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CawlError("Réponse de paiement CAWL incomplète.") from error

    def check_order(self, reference, amount, currency="EUR"):
        if (not hmac.compare_digest(self.reference, str(reference))
                or self.amount != amount or self.currency != currency):
            raise CawlError("Le paiement CAWL ne correspond pas à la commande.")


def https_url(value):
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise CawlError("Une URL HTTPS absolue est requise.")
    return value


class CawlGateway:
    def __init__(self, configuration, merchant_client=None):
        self.configuration = configuration
        self._merchant_client = merchant_client

    @contextmanager
    def merchant(self):
        if self._merchant_client is not None:
            yield self._merchant_client
            return
        from onlinepayments.sdk.communicator_configuration import CommunicatorConfiguration
        from onlinepayments.sdk.factory import Factory

        configuration = CommunicatorConfiguration(
            api_endpoint=self.configuration.endpoint,
            api_key_id=self.configuration.api_key_id,
            secret_api_key=self.configuration.api_secret,
            authorization_type="v1HMAC",
            connect_timeout=5,
            socket_timeout=20,
            integrator="TiBillet-AM-Rezal-CAWL",
        )
        with Factory.create_client_from_configuration(configuration) as client:
            yield client.merchant(self.configuration.merchant_id)

    def create_checkout(self, reference, amount, return_url, webhook_url, email):
        from onlinepayments.sdk.domain.create_hosted_checkout_request import CreateHostedCheckoutRequest

        reference = str(UUID(str(reference)))
        if type(amount) is not int or amount <= 0:
            raise CawlError("Le montant doit être un entier positif en centimes.")
        request = CreateHostedCheckoutRequest()
        request.from_dictionary({
            "order": {
                "amountOfMoney": {"amount": amount, "currencyCode": "EUR"},
                "references": {"merchantReference": reference},
                "customer": {"contactDetails": {"emailAddress": email}},
            },
            "cardPaymentMethodSpecificInput": {"authorizationMode": "SALE"},
            "hostedCheckoutSpecificInput": {
                "returnUrl": https_url(return_url),
                "locale": "fr_FR",
            },
            "feedbacks": {"webhooksUrls": [https_url(webhook_url)]},
        })
        # FR : CreateHostedCheckout n'est pas annoncé comme idempotent par CAWL.
        # EN: Do not claim idempotency for CreateHostedCheckout or retry it blindly.
        with self.merchant() as merchant:
            response = merchant.hosted_checkout().create_hosted_checkout(request).to_dictionary()
        try:
            url = response.get("redirectUrl")
            if not url:
                url = "https://payment." + response["partialRedirectUrl"]
            parsed = urlsplit(https_url(url))
            if parsed.netloc != urlsplit(self.configuration.endpoint).netloc:
                raise CawlError("URL de paiement CAWL inattendue.")
            return HostedCheckout(response["hostedCheckoutId"], url, response["RETURNMAC"])
        except (KeyError, TypeError) as error:
            raise CawlError("Réponse de création CAWL incomplète.") from error

    def get_checkout_payment(self, hosted_checkout_id):
        with self.merchant() as merchant:
            response = merchant.hosted_checkout().get_hosted_checkout(hosted_checkout_id).to_dictionary()
        payment = response.get("createdPaymentOutput", {}).get("payment")
        if payment is None:
            return None
        return PaymentSnapshot.from_dictionary(payment)

    def get_payment(self, payment_id):
        with self.merchant() as merchant:
            response = merchant.payments().get_payment(payment_id).to_dictionary()
        return PaymentSnapshot.from_dictionary(response)

    def get_refunds(self, payment_id):
        with self.merchant() as merchant:
            response = merchant.refunds().get_refunds(payment_id).to_dictionary()
        return response.get("refunds", [])

    def refund(self, payment_id, amount, operation_id):
        from onlinepayments.sdk.call_context import CallContext
        from onlinepayments.sdk.domain.refund_request import RefundRequest

        operation_id = str(UUID(str(operation_id)))
        if type(amount) is not int or amount <= 0:
            raise CawlError("Le remboursement doit être positif, en centimes.")
        request = RefundRequest()
        request.from_dictionary({"amountOfMoney": {"amount": amount, "currencyCode": "EUR"}})
        with self.merchant() as merchant:
            response = merchant.payments().refund_payment(
                payment_id, request, CallContext(idempotence_key=operation_id),
            )
        return response.to_dictionary()

    def verify_webhook(self, body, headers):
        from onlinepayments.sdk.communication.request_header import RequestHeader
        from onlinepayments.sdk.json.default_marshaller import DefaultMarshaller
        from onlinepayments.sdk.webhooks.secret_key_store import SecretKeyStore
        from onlinepayments.sdk.webhooks.secret_key_not_available_exception import SecretKeyNotAvailableException
        from onlinepayments.sdk.webhooks.webhooks_helper import WebhooksHelper

        configuration = self.configuration

        class AccountKeyStore(SecretKeyStore):
            def get_secret_key(self, key_id):
                if not hmac.compare_digest(key_id, configuration.webhook_key_id):
                    raise SecretKeyNotAvailableException(key_id, "Identifiant de webhook CAWL inconnu.")
                return configuration.webhook_secret

        request_headers = []
        for name, value in headers.items():
            request_headers.append(RequestHeader(name, value))
        helper = WebhooksHelper(DefaultMarshaller.instance(), AccountKeyStore())
        try:
            event = helper.unmarshal(body, request_headers).to_dictionary()
        except Exception as error:
            raise CawlError("Signature ou format du webhook CAWL invalide.") from error
        if event.get("merchantId") != configuration.merchant_id:
            raise CawlError("Le webhook CAWL appartient à un autre marchand.")
        if not event.get("id") or not event.get("type"):
            raise CawlError("Identifiant de webhook CAWL manquant.")
        return event
