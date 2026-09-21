#!/usr/bin/env bash
# Creates logical PostgreSQL backups from explicitly listed Gala containers.
# It publishes compressed dumps, a separate checksum list, and metadata to the
# Gala-only S3 prefix. SQL, credentials, and SecretString values never enter logs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 /etc/tibillet-gala/<slug>.conf"
load_gala_config "$CONFIG_PATH"
require_command aws
require_command docker
require_command gzip
require_command sha256sum
require_var POSTGRES_CONTAINERS

backup_id="$(utc_timestamp)"
mkdir -p "$(runtime_dir)"
work_dir="$(mktemp -d "$(runtime_dir)/backup-${backup_id}.XXXXXX")"
remote_prefix="s3://${BACKUP_BUCKET}/galas/${GALA_SLUG}/postgres/${backup_id}"
cleanup() { rm -rf "$work_dir"; }
trap cleanup EXIT

IFS=',' read -r -a containers <<< "$POSTGRES_CONTAINERS"
(( ${#containers[@]} > 0 )) || fail "POSTGRES_CONTAINERS must list at least one container"

metadata="$work_dir/metadata.txt"
checksums="$work_dir/SHA256SUMS"
printf 'gala=%s\nbackup_id=%s\nplatform=%s\ncreated_at=%s\n' \
  "$GALA_SLUG" "$backup_id" "${PLATFORM:-unknown}" "$(date -u --iso-8601=seconds)" > "$metadata"

for container in "${containers[@]}"; do
  [[ "$container" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$ ]] || fail "unsafe PostgreSQL container name"
  docker inspect "$container" >/dev/null 2>&1 || fail "PostgreSQL container not found: $container"
  [[ "$(docker inspect --format '{{.State.Running}}' "$container")" == "true" ]] || fail "PostgreSQL container is not running: $container"

  dump_file="$work_dir/${container}.sql.gz"
  # POSTGRES_DB and POSTGRES_USER remain inside the PostgreSQL container.
  docker exec "$container" sh -ec 'exec pg_dump --format=plain --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | gzip -9 > "$dump_file"
  test -s "$dump_file" || fail "empty dump from $container"
  sha256sum "$dump_file" >> "$checksums"
done
sha256sum "$metadata" >> "$checksums"

aws s3 cp --only-show-errors --recursive "$work_dir/" "$remote_prefix/"
printf '%s\n' "$backup_id" > "$(runtime_dir)/last-successful-backup"
printf 'PostgreSQL backup uploaded: gala=%s backup_id=%s databases=%s\n' "$GALA_SLUG" "$backup_id" "${#containers[@]}"
