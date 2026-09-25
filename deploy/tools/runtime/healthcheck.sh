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
