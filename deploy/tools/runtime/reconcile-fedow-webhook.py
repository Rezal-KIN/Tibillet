"""Reconcile Fedow's Stripe credentials after each Gala deployment.

Fedow reads the live keys from encrypted Configuration fields, while the Gala
runtime supplies them from Secrets Manager as environment variables. This
handles first boot and key rotation without printing credentials.
"""

import hmac
import os

from django.conf import settings
from django.db import connection
from fedow_core.models import Configuration


def ensure_secret_storage() -> None:
    """Expand upstream's 100-character columns before storing Fernet tokens.

    The pinned Fedow image declares both encrypted Stripe fields as
    varchar(100). A Fernet token for a normal live key or webhook secret can
    exceed that limit. This idempotent, versioned DDL also covers fresh Galas
    and future image upgrades that recreate the narrow columns.
    """
    table = Configuration._meta.db_table
    columns = ("stripe_endpoint_secret_enc", "stripe_api_key")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s "
            "AND column_name IN (%s, %s)",
            (table, *columns),
        )
        found = dict(cursor.fetchall())
        if set(found) != set(columns):
            raise RuntimeError("Fedow Stripe secret storage columns are missing")
        for column in columns:
            kind = found[column]
            if kind == "text":
                continue
            if kind != "character varying":
                raise RuntimeError(f"Unexpected Fedow Stripe secret storage type: {column}")
            quoted_table = connection.ops.quote_name(table)
            quoted_column = connection.ops.quote_name(column)
            cursor.execute(f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} TYPE text")


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

    ensure_secret_storage()
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
