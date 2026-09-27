#!/usr/bin/env bash
# Opt-in QR onboarding test on the non-public Smoke Gala only. No payment is made.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 SMOKE_CONFIG"
load_gala_config "$CONFIG_PATH"
[[ "$GALA_SLUG" == "gala-smoke" ]] || fail "QR E2E is restricted to gala-smoke"
require_command docker
require_command python3
docker exec fedow_django sh -lc 'test "$STRIPE_TEST" = 1 && test -n "$STRIPE_KEY_TEST"'
docker exec lespass_django sh -lc \
  'test "$STRIPE_TEST" = 1 && test "$EMAIL_BACKEND" = django.core.mail.backends.dummy.EmailBackend'

read -r qr_uuid card_number tag_id tag_uuid < <(python3 -c \
  'import secrets,uuid; print(uuid.uuid4(),secrets.token_hex(4).upper(),secrets.token_hex(4).upper(),uuid.uuid4())')

# Only this test process accepts Smoke's temporary self-signed Fedow cert.
# The running Laboutik web service keeps DEBUG=0.
docker exec -i \
  -e DEBUG=1 \
  -e QR_SMOKE_CARD_UUID="$qr_uuid" -e QR_SMOKE_CARD_NUMBER="$card_number" \
  -e QR_SMOKE_TAG_ID="$tag_id" -e QR_SMOKE_TAG_UUID="$tag_uuid" \
  laboutik_django sh -lc 'cd /DjangoFiles && poetry run python manage.py shell' \
  < "$SCRIPT_DIR/create-qr-smoke-card.py"

docker exec -e API_KEY=qr-smoke-placeholder -e RUN_QR_CARD_E2E=1 \
  -e QR_SMOKE_CARD_UUID="$qr_uuid" -e QR_SMOKE_CARD_NUMBER="$card_number" \
  lespass_django sh -lc \
  'cd /DjangoFiles && poetry run pytest -q tests/pytest/test_qr_card_fedow_e2e.py'
