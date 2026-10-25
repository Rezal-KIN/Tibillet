#!/usr/bin/env bash
# Restore is deliberately hard to invoke. Use a preview restore target first;
# production recovery requires a separately approved incident runbook.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
BACKUP_ID="${2:-}"
TARGET_CONTAINER="${3:-}"
CONFIRMATION="${4:-}"
[[ -n "$CONFIG_PATH" && -n "$BACKUP_ID" && -n "$TARGET_CONTAINER" ]] || fail "usage: $0 CONFIG BACKUP_ID TARGET_POSTGRES_CONTAINER --confirm-restore"
[[ "$CONFIRMATION" == "--confirm-restore" ]] || fail "restore requires the literal --confirm-restore acknowledgement"
load_gala_config "$CONFIG_PATH"
require_command aws
require_command docker
require_command gzip
require_command sha256sum
[[ "${ALLOW_RESTORE:-false}" == "true" ]] || fail "ALLOW_RESTORE=true must be set in the root-owned gala config"
[[ "$TARGET_CONTAINER" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$ ]] || fail "unsafe PostgreSQL container name"
[[ "$BACKUP_ID" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || fail "backup ID has an invalid format"

docker inspect "$TARGET_CONTAINER" >/dev/null 2>&1 || fail "target PostgreSQL container not found"
work_dir="$(mktemp -d "$(runtime_dir)/restore-${BACKUP_ID}.XXXXXX")"
cleanup() { rm -rf "$work_dir"; }
trap cleanup EXIT
remote_prefix="s3://${BACKUP_BUCKET}/galas/${GALA_SLUG}/postgres/${BACKUP_ID}"

aws s3 cp --only-show-errors --recursive "$remote_prefix/" "$work_dir/"
[[ -f "$work_dir/metadata.txt" && -f "$work_dir/SHA256SUMS" ]] || fail "backup metadata is incomplete"
(cd "$work_dir" && sha256sum -c SHA256SUMS >/dev/null)

dump_file="$work_dir/${TARGET_CONTAINER}.sql.gz"
[[ -f "$dump_file" ]] || fail "backup has no dump for the requested target container"

# The selected target must be a dedicated restore database. The script never
# drops/recreates a database and fails at the first SQL error.
gzip -dc "$dump_file" | docker exec -i "$TARGET_CONTAINER" sh -ec 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'
printf 'Restore completed: gala=%s backup_id=%s target=%s\n' "$GALA_SLUG" "$BACKUP_ID" "$TARGET_CONTAINER"
