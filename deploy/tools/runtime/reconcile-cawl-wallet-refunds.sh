#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 CONFIG"
load_gala_config "$CONFIG_PATH"
[[ "${PAYMENT_PROVIDER:-stripe}" == cawl ]] || exit 0
require_command docker
# A timer from an older release must never process another running image.
load_release_images "$(deployed_manifest_path)"
[[ "$(docker inspect --format '{{.State.Running}}' fedow_django)" == true ]] || exit 0
[[ "$(docker inspect --format '{{.Config.Image}}' fedow_django)" == "$FEDOW_IMAGE" ]] || fail "Fedow image differs from the deployed manifest"
docker exec fedow_django poetry run python manage.py reconcile_cawl_wallet_refunds --limit 100
