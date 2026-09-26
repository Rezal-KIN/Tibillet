#!/usr/bin/env bash
# Restore each Gala PostgreSQL dump into a disposable, network-isolated
# container. Never connects to or writes into a live database.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
BACKUP_ID="${2:-}"
[[ -n "$CONFIG_PATH" && "$BACKUP_ID" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] \
  || fail "usage: $0 CONFIG BACKUP_ID (YYYYMMDDTHHMMSSZ)"
load_gala_config "$CONFIG_PATH"
require_command aws
require_command docker
require_command gzip
require_command sha256sum
require_command timeout
require_var POSTGRES_CONTAINERS

umask 077
mkdir -p "$(runtime_dir)"
work_dir="$(mktemp -d "$(runtime_dir)/restore-drill-${BACKUP_ID}.XXXXXX")"
drill_container=""
cleanup() {
  if [[ -n "$drill_container" ]]; then
    docker rm -f "$drill_container" >/dev/null 2>&1 || true
  fi
  [[ "$work_dir" == "$(runtime_dir)/restore-drill-${BACKUP_ID}."* ]] \
    || fail "unsafe restore drill temporary path"
  rm -rf -- "$work_dir"
}
trap cleanup EXIT

remote_prefix="s3://${BACKUP_BUCKET}/galas/${GALA_SLUG}/postgres/${BACKUP_ID}"
aws s3 cp --only-show-errors --recursive "$remote_prefix/" "$work_dir/"
[[ -f "$work_dir/metadata.txt" && -f "$work_dir/SHA256SUMS" ]] \
  || fail "backup metadata is incomplete"
grep -Fxq "gala=${GALA_SLUG}" "$work_dir/metadata.txt" || fail "backup belongs to another Gala"
grep -Fxq "backup_id=${BACKUP_ID}" "$work_dir/metadata.txt" || fail "backup ID does not match metadata"
(cd "$work_dir" && sha256sum -c SHA256SUMS >/dev/null)

IFS=',' read -r -a source_containers <<< "$POSTGRES_CONTAINERS"
(( ${#source_containers[@]} > 0 )) || fail "POSTGRES_CONTAINERS is empty"
for source_container in "${source_containers[@]}"; do
  [[ "$source_container" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$ ]] \
    || fail "unsafe PostgreSQL container name"
  dump_file="$work_dir/${source_container}.sql.gz"
  [[ -s "$dump_file" ]] || fail "backup has no dump for $source_container"
  gzip -t "$dump_file"
  image="$(docker inspect --format '{{.Config.Image}}' "$source_container")"
  [[ "$image" == postgres:* ]] || fail "unexpected PostgreSQL image for $source_container"

  # No host volume, published port, or network access; the restored data is
  # confined to container tmpfs and disappears when the drill ends.
  drill_container="$(docker run --rm -d --network none --memory 512m --cpus 0.5 \
    --tmpfs /tmp:rw,size=256m -e PGDATA=/tmp/pgdata \
    -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_USER=postgres \
    -e POSTGRES_DB=restoretest "$image")"
  ready=false
  for attempt in {1..30}; do
    if docker exec "$drill_container" pg_isready -U postgres -d restoretest >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 1
  done
  [[ "$ready" == true ]] || fail "isolated PostgreSQL did not start for $source_container"
  gzip -dc "$dump_file" | timeout 120s docker exec -i "$drill_container" \
    psql -v ON_ERROR_STOP=1 -U postgres -d restoretest >/dev/null
  table_count="$(docker exec "$drill_container" psql -At -U postgres -d restoretest \
    -c "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')")"
  [[ "$table_count" =~ ^[0-9]+$ && "$table_count" -gt 0 ]] \
    || fail "restore produced no application tables for $source_container"
  docker rm -f "$drill_container" >/dev/null
  drill_container=""
  printf 'Isolated restore verified: gala=%s backup_id=%s source=%s tables=%s\n' \
    "$GALA_SLUG" "$BACKUP_ID" "$source_container" "$table_count"
done
