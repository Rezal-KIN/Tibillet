"""Reconcile Fedow's Stripe credentials after each Gala deployment.

Fedow reads the live keys from encrypted Configuration fields, while the Gala
runtime supplies them from Secrets Manager as environment variables. This
handles first boot and key rotation without printing credentials.
"""

import hmac
import os

from django.conf import settings
from fedow_core.models import Configuration


def reconcile() -> None:
    name = "STRIPE_ENDPOINT_SECRET_TEST" if settings.STRIPE_TEST else "STRIPE_ENDPOINT_SECRET"
    expected = os.environ.get(name, "")
    if not expected.startswith("whsec_"):
        raise RuntimeError(f"Fedow {name} is missing or invalid")
    api_name = "STRIPE_KEY_TEST" if settings.STRIPE_TEST else "STRIPE_KEY"
    expected_api = os.environ.get(api_name, "")
    prefix = "sk_test_" if settings.STRIPE_TEST else "sk_live_"
    if not expected_api.startswith(prefix):
        raise RuntimeError(f"Fedow {api_name} is missing or invalid")

    config = Configuration.get_solo()
    if not settings.STRIPE_TEST:
        current = config.get_stripe_endpoint_secret() if config.stripe_endpoint_secret_enc else ""
        if not hmac.compare_digest(current, expected):
            config.set_stripe_endpoint_secret(expected)
        current_api = config.get_stripe_api() if config.stripe_api_key else ""
        if not hmac.compare_digest(current_api, expected_api):
            config.set_stripe_api(expected_api)

    # Verify through the same accessor used by Fedow's webhook permission.
    actual = config.get_stripe_endpoint_secret()
    if not actual or not hmac.compare_digest(actual, expected):
        raise RuntimeError("Fedow webhook secret reconciliation failed")
    actual_api = config.get_stripe_api()
    if not actual_api or not hmac.compare_digest(actual_api, expected_api):
        raise RuntimeError("Fedow Stripe API key reconciliation failed")
    print("Fedow Stripe credentials ready")


reconcile()
