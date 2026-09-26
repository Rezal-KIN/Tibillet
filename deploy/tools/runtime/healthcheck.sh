#!/usr/bin/env bash
# Checks explicit, non-secret endpoints after boot or deployment.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 CONFIG"
load_gala_config "$CONFIG_PATH"
require_command curl
require_command docker
require_command timeout
require_var HEALTHCHECK_URLS

IFS=',' read -r -a urls <<< "$HEALTHCHECK_URLS"
(( ${#urls[@]} > 0 )) || fail "HEALTHCHECK_URLS must contain at least one URL"
for url in "${urls[@]}"; do
  [[ "$url" =~ ^https://([a-z0-9.-]+)(/.*)?$ ]] || fail "healthcheck URL must be HTTPS on a configured Gala domain"
  host="${BASH_REMATCH[1]}"
  case "$host" in
    "$FEDOW_PUBLIC_DOMAIN"|"$LABOUTIK_PUBLIC_DOMAIN"|"$LESPASS_PUBLIC_DOMAIN") ;;
    *) fail "healthcheck URL targets a different Gala domain" ;;
  esac
  # Each Gala may use the same public hostnames. Resolve to this machine so
  # an inactive host can never pass by checking the currently active Gala.
  # Certificate trust is verified separately after the shared EIP is moved.
  status="$(curl --silent --show-error --insecure --noproxy '*' \
    --resolve "$host:443:127.0.0.1" --max-time 20 --max-redirs 0 \
    --output /dev/null --write-out '%{http_code}' "$url")"
  case "$status" in
    200|301|302) printf 'local healthy url=%s status=%s\n' "$url" "$status" ;;
    *) fail "healthcheck failed url=$url status=$status" ;;
  esac
done

# A 200 response from the generic TiBillet public homepage is not a healthy
# Gala site. Verify the Django tenant mapping as well as the HTTP endpoint.
timeout 30s docker exec -w /DjangoFiles lespass_django \
  /home/tibillet/.local/bin/poetry run python manage.py configure_gala_apex --check \
  >/dev/null || fail "Lespass apex is not mapped to the Gala tenant"

# A healthy HTTP response is insufficient when email login cannot send its
# activation link. Django expects real booleans, not truthy strings like "0".
timeout 15s docker exec -w /DjangoFiles lespass_django \
  /home/tibillet/.local/bin/poetry run python manage.py shell -c \
  'from django.conf import settings; assert isinstance(settings.EMAIL_USE_TLS, bool) and isinstance(settings.EMAIL_USE_SSL, bool) and not (settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL)' \
  >/dev/null || fail "Lespass SMTP TLS/SSL settings are invalid"

# Laboutik's upstream entrypoint can keep serving its login page even if its
# install command failed. Require the seeded payment setup and admin account.
timeout 15s docker exec -w /DjangoFiles laboutik_django \
  /home/tibillet/.local/bin/poetry run python manage.py shell -c \
  'import os; from django.contrib.auth import get_user_model; from APIcashless.models import PointDeVente; assert PointDeVente.objects.exists() and get_user_model().objects.filter(email=os.environ["ADMIN_EMAIL"], is_staff=True).exists()' \
  >/dev/null || fail "Laboutik installation or admin account is missing"

timeout 15s docker exec lespass_django curl --fail --silent --show-error \
  --header "Host: $FEDOW_PUBLIC_DOMAIN" http://fedow_nginx/helloworld/ \
  >/dev/null || fail "Lespass cannot reach its local Fedow service"

# HTTP can stay healthy while the Lespass background worker crashes. A release
# is only healthy when the worker is running and responds through its broker.
[[ "$(docker inspect --format '{{.State.Running}}' lespass_celery 2>/dev/null || true)" == "true" ]] \
  || fail "Lespass Celery worker is not running"
timeout 15s docker exec -w /DjangoFiles lespass_django \
  /home/tibillet/.local/bin/poetry run celery -A TiBillet inspect ping --timeout=5 \
  >/dev/null 2>&1 || fail "Lespass Celery worker did not answer broker ping"
printf 'local healthy service=lespass_celery status=responsive\n'
