#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 CONFIG"
load_gala_config "$CONFIG_PATH"
require_command docker
require_var COMPOSE_FILES

load_release_images "$(deployed_manifest_path)"
write_compose_environment

docker network inspect frontend >/dev/null 2>&1 || docker network create frontend >/dev/null
IFS=':' read -r -a compose_groups <<< "$COMPOSE_FILES"
for group in "${compose_groups[@]}"; do
  compose_group_args "$group"
  docker compose --env-file "$(compose_env_file)" "${COMPOSE_ARGS[@]}" up -d
done
