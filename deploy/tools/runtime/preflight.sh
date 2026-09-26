#!/usr/bin/env bash
# Fails closed before a deployment. This contains no migration, restart, or
# cleanup logic: it only reports whether a release is safe to attempt.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
MANIFEST_PATH="${2:-}"
[[ -n "$CONFIG_PATH" && -n "$MANIFEST_PATH" ]] || fail "usage: $0 CONFIG RELEASE_MANIFEST"
load_gala_config "$CONFIG_PATH"
require_command docker
require_command python3
require_var COMPOSE_FILES
require_var POSTGRES_CONTAINERS

[[ "${DEPLOYMENT_LOCKED:-true}" != "true" ]] || fail "deployment is locked for gala $GALA_SLUG"
python3 "$SCRIPT_DIR/validate-release.py" "$MANIFEST_PATH"
manifest_slug="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["gala_slug"])' "$MANIFEST_PATH")"
[[ "$manifest_slug" == "$GALA_SLUG" ]] || fail "manifest gala slug does not match runtime configuration"
load_release_images "$MANIFEST_PATH"
write_compose_environment

last_backup_file="$(runtime_dir)/last-successful-backup"
if [[ -s "$last_backup_file" ]]; then
  last_backup="$(cat "$last_backup_file")"
  [[ "$last_backup" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || fail "backup marker is invalid"
  backup_epoch="$(date -u -d "${last_backup:0:8} ${last_backup:9:2}:${last_backup:11:2}:${last_backup:13:2}" +%s 2>/dev/null || true)"
  now_epoch="$(date -u +%s)"
  [[ -n "$backup_epoch" ]] || fail "cannot parse backup timestamp"
  (( now_epoch - backup_epoch <= ${MAX_BACKUP_AGE_SECONDS:-86400} )) || fail "latest backup is too old"
else
  # A missing backup is acceptable only before the first successful release.
  # The bootstrap keeps ALLOW_INITIAL_DEPLOY=true in its immutable config, so
  # that flag alone must never bypass backup checks on later deployments.
  [[ "${ALLOW_INITIAL_DEPLOY:-false}" == "true" && ! -e "$(deployed_manifest_path)" ]] \
    || fail "no successful backup marker exists"
  last_backup="initial-deployment"
fi

# Docker images need workspace both while pulled and while old images remain.
avail_kib="$(df -Pk "${REPO_ROOT}" | awk 'NR == 2 { print $4 }')"
(( avail_kib >= ${MIN_FREE_SPACE_KIB:-10485760} )) || fail "less than required free space remains"

IFS=':' read -r -a compose_groups <<< "$COMPOSE_FILES"
for group in "${compose_groups[@]}"; do
  compose_group_args "$group"
  docker compose --env-file "$(compose_env_file)" "${COMPOSE_ARGS[@]}" config --quiet
done

printf 'Preflight passed: gala=%s platform=%s backup=%s\n' "$GALA_SLUG" "$PLATFORM" "$last_backup"
