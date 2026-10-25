#!/usr/bin/env bash
# Keep the deployment reserve on a small host without deleting application
# data. Docker only prunes images unused by every existing container.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 CONFIG"
load_gala_config "$CONFIG_PATH"
require_command docker
require_command df

min_free_kib="${MIN_FREE_SPACE_KIB:-10485760}"
[[ "$min_free_kib" =~ ^[0-9]+$ ]] || fail "MIN_FREE_SPACE_KIB must be an integer"
free_kib="$(df -Pk "$REPO_ROOT" | awk 'NR == 2 { print $4 }')"
[[ "$free_kib" =~ ^[0-9]+$ ]] || fail "cannot measure free disk space"
if (( free_kib < min_free_kib )); then
  printf 'Low disk space: reclaiming unused Docker images before preflight\n'
  docker image prune --all --force >/dev/null
  free_kib="$(df -Pk "$REPO_ROOT" | awk 'NR == 2 { print $4 }')"
  [[ "$free_kib" =~ ^[0-9]+$ ]] || fail "cannot measure free disk space after cleanup"
fi
(( free_kib >= min_free_kib )) || fail "less than required free space remains after unused-image cleanup"
