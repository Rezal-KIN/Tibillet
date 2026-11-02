"""Permit native Fedow without Stripe only when CAWL is the selected provider.

Fedow already supports operating without Stripe. The unconditional startup
checks prevent using DEBUG=0 even though online payment is handled by Lespass.
No payment keys, API behavior or debug settings are changed by this overlay.
"""
from pathlib import Path


def patch(source, original):
    if source.count(original) != 1:
        raise ValueError("Native Fedow Stripe guard differs from the reviewed source")
    condition = original[:-1] + " and os.environ.get('PAYMENT_PROVIDER', 'stripe') != 'cawl':"
    return source.replace(original, condition, 1)


if __name__ == "__main__":
    root = Path("/home/fedow/Fedow")
    for relative, original in (
        ("fedowallet_django/settings.py", "if not STRIPE_KEY_TEST and not STRIPE_KEY and not DEBUG:"),
        ("fedow_core/management/commands/install.py", "if not os.environ.get('STRIPE_KEY_TEST') and not os.environ.get('STRIPE_KEY') and not settings.DEBUG:"),
    ):
        path = root / relative
        path.write_text(patch(path.read_text(), original))
