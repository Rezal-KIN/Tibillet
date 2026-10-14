"""Contrat API, signatures et montants : aucun appel réseau. / No network calls."""

import base64
import hashlib
import hmac
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from payment_providers.cawl import CawlConfiguration, CawlError, CawlGateway, PaymentSnapshot


@pytest.fixture
def config():
    return CawlConfiguration("merchant-test", "key-test", "api-secret-test", "hook-test", "hook-secret-test", True)


def payment(reference, status="CAPTURED", amount=2000, currency="EUR"):
    return {
        "id": "payment-001", "status": status,
        "paymentOutput": {"amountOfMoney": {"amount": amount, "currencyCode": currency},
                          "references": {"merchantReference": str(reference)}},
    }


@pytest.mark.parametrize("status", ["CREATED", "PENDING_APPROVAL", "AUTHORIZATION_REQUESTED", "CAPTURE_REQUESTED", "REJECTED", "CANCELLED", "REFUNDED"])
def test_only_captured_can_credit_wallet(status):
    snapshot = PaymentSnapshot.from_dictionary(payment(uuid4(), status))
    assert not snapshot.captured


def test_captured_requires_exact_reference_amount_currency():
    reference = uuid4()
    snapshot = PaymentSnapshot.from_dictionary(payment(reference))
    snapshot.check_order(reference, 2000)
    assert snapshot.captured
    for other_reference, other_amount, currency in [(uuid4(), 2000, "EUR"), (reference, 2001, "EUR"), (reference, 2000, "USD")]:
        with pytest.raises(CawlError):
            snapshot.check_order(other_reference, other_amount, currency)


@pytest.mark.parametrize("amount", [0, -1, True, 2.5, "2000"])
def test_non_integer_provider_amount_rejected(amount):
    with pytest.raises(CawlError):
        PaymentSnapshot.from_dictionary(payment(uuid4(), amount=amount))


def signed_event(configuration, merchant=None):
    body = json.dumps({
        "apiVersion": "v1", "id": str(uuid4()), "type": "payment.captured",
        "merchantId": merchant or configuration.merchant_id,
        "payment": payment(uuid4()),
    }, separators=(",", ":")).encode()
    signature = base64.b64encode(hmac.new(configuration.webhook_secret.encode(), body, hashlib.sha256).digest()).decode()
    return body, {"X-GCS-KeyId": configuration.webhook_key_id, "X-GCS-Signature": signature}


def test_valid_signature_uses_raw_body(config):
    gateway = CawlGateway(config)
    body, headers = signed_event(config)
    assert gateway.verify_webhook(body, headers)["type"] == "payment.captured"
    with pytest.raises(CawlError):
        gateway.verify_webhook(body + b" ", headers)


def test_wrong_merchant_wrong_key_and_missing_signature_rejected(config):
    gateway = CawlGateway(config)
    body, headers = signed_event(config, merchant="other-merchant")
    with pytest.raises(CawlError):
        gateway.verify_webhook(body, headers)
    body, headers = signed_event(config)
    headers["X-GCS-KeyId"] = "unknown-key"
    with pytest.raises(CawlError):
        gateway.verify_webhook(body, headers)
    with pytest.raises(CawlError):
        gateway.verify_webhook(body, {})


def test_accounts_do_not_share_webhook_keys(config):
    other = CawlConfiguration("other", "key", "secret", "other-hook", "other-secret", True)
    CawlGateway(other).verify_webhook(*signed_event(other))
    with pytest.raises(CawlError):
        CawlGateway(config).verify_webhook(*signed_event(other))


def test_secret_values_not_in_configuration_representation(config):
    representation = repr(config)
    for value in [config.api_key_id, config.api_secret, config.webhook_key_id, config.webhook_secret]:
        assert value not in representation


@pytest.mark.parametrize("mode,expected", [("1", "https://payment.preprod.cawl-solutions.fr"), ("0", "https://payment.cawl-solutions.fr")])
def test_environment_is_explicit_and_separate(mode, expected):
    environment = {"CAWL_TEST": mode, "CAWL_MERCHANT_ID": "merchant", "CAWL_API_KEY_ID": "key",
                   "CAWL_API_SECRET": "secret", "CAWL_WEBHOOK_KEY_ID": "hook", "CAWL_WEBHOOK_SECRET": "hook-secret"}
    assert CawlConfiguration.from_environment(environment).endpoint == expected
    environment["CAWL_TEST"] = "false"
    with pytest.raises(CawlError):
        CawlConfiguration.from_environment(environment)
    del environment["CAWL_API_SECRET"]
    with pytest.raises(CawlError):
        CawlConfiguration.from_environment(environment)


def test_hosted_checkout_serializes_official_sdk_objects(config):
    from onlinepayments.sdk.domain.create_hosted_checkout_response import CreateHostedCheckoutResponse

    sent = []
    def create(request):
        sent.append(request.to_dictionary())
        return CreateHostedCheckoutResponse().from_dictionary({
            "hostedCheckoutId": "hosted-001", "RETURNMAC": "mac-test",
            "partialRedirectUrl": "preprod.cawl-solutions.fr/hostedcheckout/001",
        })
    merchant = SimpleNamespace(hosted_checkout=lambda: SimpleNamespace(create_hosted_checkout=create))
    reference = uuid4()
    checkout = CawlGateway(config, merchant).create_checkout(reference, 2000, "https://gala.example/return/", "https://fedow.example/webhook_cawl/", "test@example.test")
    assert checkout.url == "https://payment.preprod.cawl-solutions.fr/hostedcheckout/001"
    assert sent[0]["order"]["references"]["merchantReference"] == str(reference)
    assert sent[0]["order"]["amountOfMoney"] == {"amount": 2000, "currencyCode": "EUR"}
    assert sent[0]["cardPaymentMethodSpecificInput"]["authorizationMode"] == "SALE"
    assert sent[0]["feedbacks"]["webhooksUrls"] == ["https://fedow.example/webhook_cawl/"]


def test_refund_has_stable_idempotence_key_and_amount(config):
    from onlinepayments.sdk.domain.refund_response import RefundResponse

    sent = []
    def refund(payment_id, request, context):
        sent.append((payment_id, request.to_dictionary(), context.idempotence_key))
        return RefundResponse().from_dictionary({"id": "refund-001", "status": "REFUND_REQUESTED"})
    merchant = SimpleNamespace(payments=lambda: SimpleNamespace(refund_payment=refund))
    operation = uuid4()
    result = CawlGateway(config, merchant).refund("payment-001", 500, operation)
    assert result["status"] == "REFUND_REQUESTED"
    assert sent == [("payment-001", {"amountOfMoney": {"amount": 500, "currencyCode": "EUR"}}, str(operation))]


def test_no_payment_created_is_pending(config):
    from onlinepayments.sdk.domain.get_hosted_checkout_response import GetHostedCheckoutResponse

    merchant = SimpleNamespace(hosted_checkout=lambda: SimpleNamespace(
        get_hosted_checkout=lambda checkout_id: GetHostedCheckoutResponse().from_dictionary({"status": "IN_PROGRESS"})))
    assert CawlGateway(config, merchant).get_checkout_payment("hosted-001") is None
