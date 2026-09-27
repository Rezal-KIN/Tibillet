"""Create a disposable Smoke card through Laboutik's signed Fedow API.

This file is fed to Laboutik's ``manage.py shell`` by run-qr-smoke-e2e.sh.
Lespass has the place API key but not Laboutik's RSA private key; using its
unsigned card-create API in the QR test works only before cashless pairing.
"""

import os

from APIcashless.models import Configuration
from fedow_connect.fedow_api import _post


# Laboutik runs Django 2.2, whose shell command calls exec(stdin.read()) from
# inside a function. Keep this at top level: a function defined by that exec
# cannot resolve the imported _post through its module globals.
card = {
    "first_tag_id": os.environ["QR_SMOKE_TAG_ID"],
    "complete_tag_id_uuid": os.environ["QR_SMOKE_TAG_UUID"],
    "qrcode_uuid": os.environ["QR_SMOKE_CARD_UUID"],
    "number_printed": os.environ["QR_SMOKE_CARD_NUMBER"],
    "generation": 1,
    "is_primary": False,
}
response = _post(Configuration.get_solo(), "card", [card])
if response.status_code != 201:
    raise RuntimeError(f"signed Smoke card creation failed: HTTP {response.status_code}")
print("Signed Smoke NFC card created")
