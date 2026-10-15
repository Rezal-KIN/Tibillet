#!/usr/bin/env bash
# Opt-in QR onboarding test on either Smoke Gala. No payment is made.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 SMOKE_CONFIG"
load_gala_config "$CONFIG_PATH"
case "$GALA_SLUG" in gala-smoke|gala-smoke-cawl) ;; *) fail "QR E2E requires a Smoke Gala" ;; esac
require_command docker
require_command python3
for application in fedow_django lespass_django; do
  docker exec "$application" sh -lc '
    case "$PAYMENT_PROVIDER" in
      stripe) test "$STRIPE_TEST" = 1 && test -n "$STRIPE_KEY_TEST" ;;
      cawl) test "$CAWL_TEST" = 1 && test -n "$CAWL_API_KEY_ID" ;;
      *) exit 1 ;;
    esac'
done
docker exec lespass_django sh -lc '
  case "$EMAIL_BACKEND" in
    django.core.mail.backends.dummy.EmailBackend) ;;
    gala_mail.TestRecipientEmailBackend) test -n "$GALA_TEST_MAIL_RECIPIENT" ;;
    *) exit 1 ;;
  esac'

read -r qr_uuid card_number tag_id tag_uuid < <(python3 -c \
  'import secrets,uuid; print(uuid.uuid4(),secrets.token_hex(4).upper(),secrets.token_hex(4).upper(),uuid.uuid4())')

# Only this test process accepts Smoke's temporary self-signed Fedow cert.
# The running Laboutik web service keeps DEBUG=0.
timeout 120s docker exec -i \
  -e DEBUG=1 \
  -e QR_SMOKE_CARD_UUID="$qr_uuid" -e QR_SMOKE_CARD_NUMBER="$card_number" \
  -e QR_SMOKE_TAG_ID="$tag_id" -e QR_SMOKE_TAG_UUID="$tag_uuid" \
  laboutik_django sh -lc 'cd /DjangoFiles && poetry run python manage.py shell' \
  < "$SCRIPT_DIR/create-qr-smoke-card.py"

timeout 600s docker exec -e API_KEY=qr-smoke-placeholder -e RUN_QR_CARD_E2E=1 \
  -e EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend \
  -e QR_SMOKE_CARD_UUID="$qr_uuid" -e QR_SMOKE_CARD_NUMBER="$card_number" \
  lespass_django sh -lc \
  'cd /DjangoFiles && poetry run pytest -q tests/pytest/test_qr_card_fedow_e2e.py'
