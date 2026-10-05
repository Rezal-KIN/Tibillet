#!/usr/bin/env bash
# Backs up PostgreSQL plus native Fedow SQLite in the historical S3 prefix.
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
require_command python3
require_var POSTGRES_CONTAINERS

backup_id="$(utc_timestamp)"
umask 077
mkdir -p "$(runtime_dir)"
work_dir="$(mktemp -d "$(runtime_dir)/backup-${backup_id}.XXXXXX")"
remote_prefix="s3://${BACKUP_BUCKET}/galas/${GALA_SLUG}/postgres/${backup_id}"
cleanup() { rm -rf "$work_dir"; }
trap cleanup EXIT

IFS=',' read -r -a configured_containers <<< "$POSTGRES_CONTAINERS"
containers=()
for container in "${configured_containers[@]}"; do
  # Old host configs still list Fedow PostgreSQL. Its actual running storage
  # decides what to back up, so a stale config cannot skip the SQLite wallet.
  [[ "$container" == fedow_postgres ]] || containers+=("$container")
done
fedow_mount="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/home/fedow/Fedow/database"}}{{.Source}}{{end}}{{end}}' fedow_django)"
if [[ -n "$fedow_mount" ]]; then
  [[ "$fedow_mount" == "$REPO_ROOT/deploy/Fedow/sqlite-database" ]] || fail "unexpected Fedow SQLite storage mount"
  python3 "$SCRIPT_DIR/fedow-sqlite.py" snapshot "$fedow_mount/db.sqlite3" "$work_dir/fedow.sqlite3" >/dev/null
  gzip -9 "$work_dir/fedow.sqlite3"
  (cd "$work_dir" && sha256sum fedow.sqlite3.gz >> SHA256SUMS)
else
  # Works before cutover too, even with the new two-container config.
  containers+=(fedow_postgres)
fi
(( ${#containers[@]} > 0 )) || fail "POSTGRES_CONTAINERS must list at least one container"

metadata="$work_dir/metadata.txt"
printf 'gala=%s\nbackup_id=%s\nplatform=%s\ncreated_at=%s\n' \
  "$GALA_SLUG" "$backup_id" "${PLATFORM:-unknown}" "$(date -u --iso-8601=seconds)" > "$metadata"
printf 'backup_format=2\nfedow_sqlite=%s\n' "$([[ -n "$fedow_mount" ]] && echo 1 || echo 0)" >> "$metadata"

for container in "${containers[@]}"; do
  [[ "$container" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$ ]] || fail "unsafe PostgreSQL container name"
  docker inspect "$container" >/dev/null 2>&1 || fail "PostgreSQL container not found: $container"
  [[ "$(docker inspect --format '{{.State.Running}}' "$container")" == "true" ]] || fail "PostgreSQL container is not running: $container"
  image="$(docker inspect --format '{{.Config.Image}}' "$container")"
  [[ "$image" == postgres:* ]] || fail "unexpected PostgreSQL image for $container"
  printf 'postgres_container=%s\npostgres_image_%s=%s\n' "$container" "$container" "$image" >> "$metadata"

  dump_file="$work_dir/${container}.sql.gz"
  # POSTGRES_DB and POSTGRES_USER remain inside the PostgreSQL container.
  docker exec "$container" sh -ec 'exec pg_dump --format=plain --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | gzip -9 > "$dump_file"
  test -s "$dump_file" || fail "empty dump from $container"
  (cd "$work_dir" && sha256sum "${container}.sql.gz" >> SHA256SUMS)
done
(cd "$work_dir" && sha256sum metadata.txt >> SHA256SUMS)

aws s3 cp --only-show-errors --recursive "$work_dir/" "$remote_prefix/"
printf '%s\n' "$backup_id" > "$(runtime_dir)/last-successful-backup"
printf 'Database backup uploaded: gala=%s backup_id=%s postgres=%s sqlite=%s\n' "$GALA_SLUG" "$backup_id" "${#containers[@]}" "$([[ -n "$fedow_mount" ]] && echo 1 || echo 0)"
