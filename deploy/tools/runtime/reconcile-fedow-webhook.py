"""Reconcile Fedow's webhook signing secret after each Gala deployment.

Fedow reads the live secret from its encrypted Configuration row, while the
Gala runtime supplies it from Secrets Manager as an environment variable.
This also handles first boot and key rotation without printing the secret.
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

    ensure_secret_storage()
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
