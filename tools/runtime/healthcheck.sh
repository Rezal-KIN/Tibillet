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
  status="$(curl --silent --show-error --location --max-time 20 --output /dev/null --write-out '%{http_code}' "$url")"
  case "$status" in
    200|301|302) printf 'healthy url=%s status=%s\n' "$url" "$status" ;;
    *) fail "healthcheck failed url=$url status=$status" ;;
  esac
done
