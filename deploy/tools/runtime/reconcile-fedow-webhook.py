"""Reconcile Fedow's webhook signing secret after each Gala deployment.

Fedow reads the live secret from its encrypted Configuration row, while the
Gala runtime supplies it from Secrets Manager as an environment variable.
This also handles first boot and key rotation without printing the secret.
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

    config = Configuration.get_solo()
    if not settings.STRIPE_TEST:
        current = config.get_stripe_endpoint_secret() if config.stripe_endpoint_secret_enc else ""
        if not hmac.compare_digest(current, expected):
            config.set_stripe_endpoint_secret(expected)

    # Verify through the same accessor used by Fedow's webhook permission.
    actual = config.get_stripe_endpoint_secret()
    if not actual or not hmac.compare_digest(actual, expected):
        raise RuntimeError("Fedow webhook secret reconciliation failed")
    print("Fedow Stripe webhook secret ready")


reconcile()
