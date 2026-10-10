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

# A 200 homepage can still render without its styles after storage preparation.
# Require the homepage stylesheets from this host's Nginx.
for asset in bootstrap.min.5.3.3.css bootstrap-icons.min.css vars.css tibillet.css swal.css; do
  url="https://$LESPASS_PUBLIC_DOMAIN/static/reunion/css/$asset"
  status="$(curl --silent --show-error --insecure --noproxy '*' \
    --resolve "$LESPASS_PUBLIC_DOMAIN:443:127.0.0.1" --max-time 20 --max-redirs 0 \
    --output /dev/null --write-out '%{http_code}' "$url")"
  [[ "$status" == 200 ]] || fail "Lespass stylesheet unavailable url=$url status=$status"
  printf 'local healthy stylesheet=%s status=%s\n' "$asset" "$status"
done

# A 200 response from the generic TiBillet public homepage is not a healthy
# Gala site. Verify the Django tenant mapping as well as the HTTP endpoint.
timeout 30s docker exec -w /DjangoFiles lespass_django \
  /home/tibillet/.local/bin/poetry run python manage.py configure_gala_apex --check \
  >/dev/null || fail "Lespass apex is not mapped to the Gala tenant"

python3 "$SCRIPT_DIR/configure-gala-refill-domain.py" --domain "$LESPASS_PUBLIC_DOMAIN" --check \
  >/dev/null || fail "Fedow refill return domain is not the Lespass apex"

timeout 30s docker exec -w /DjangoFiles lespass_django \
  /home/tibillet/.local/bin/poetry run python manage.py configure_gala_refill --check \
  >/dev/null || fail "Gala QR-card refill action is not visible"

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

# Both processes select the same local Fedow transport. A web-only check
# previously missed the worker's absent shared Docker network.
for client in lespass_django lespass_celery; do
  timeout 15s docker exec "$client" curl --fail --silent --show-error \
    --connect-timeout 3 --max-time 10 \
    --header "Host: $FEDOW_PUBLIC_DOMAIN" http://fedow_nginx/helloworld/ \
    >/dev/null || fail "$client cannot reach its local Fedow service"
done

# Verify peer routing from the actual application containers. DNS must target
# the host gateway, not the currently active Gala's public address. HTTPS is
# checked on the host above; inactive first boots may still have Traefik's
# temporary certificate, whose trust is checked after activation.
for client in lespass_django lespass_celery; do
  timeout 15s docker exec "$client" python -c \
    'import socket,sys; assert socket.gethostbyname(sys.argv[1]) == socket.gethostbyname(sys.argv[2])' \
    "$LABOUTIK_PUBLIC_DOMAIN" "$FEDOW_PUBLIC_DOMAIN" \
    >/dev/null || fail "$client cashless domain is not routed to the local gateway"
done
timeout 15s docker exec fedow_django python -c \
  'import socket,sys; addresses=[line.split()[0] for line in open("/etc/hosts") if sys.argv[1] in line.split()[1:]]; assert addresses and socket.gethostbyname(sys.argv[1]) in addresses' \
  "$LESPASS_PUBLIC_DOMAIN" \
  >/dev/null || fail "Fedow Lespass callback domain is not locally mapped"

# HTTP can stay healthy while the Lespass background worker crashes. A release
# is only healthy when the worker is running and responds through its broker.
[[ "$(docker inspect --format '{{.State.Running}}' lespass_celery 2>/dev/null || true)" == "true" ]] \
  || fail "Lespass Celery worker is not running"
timeout 15s docker exec -w /DjangoFiles lespass_django \
  /home/tibillet/.local/bin/poetry run celery -A TiBillet inspect ping --timeout=5 \
  >/dev/null 2>&1 || fail "Lespass Celery worker did not answer broker ping"
printf 'local healthy service=lespass_celery status=responsive\n'
python3 "$SCRIPT_DIR/configure-gala-admin.py" --gala "$GALA_SLUG" \
  --credentials-file "$(runtime_dir)/admin.json" >/dev/null \
  || fail "shared administrator accounts are not configured"
