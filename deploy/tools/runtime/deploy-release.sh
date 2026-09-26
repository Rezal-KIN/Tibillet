#!/usr/bin/env bash
# Deployment entrypoint installed through the bootstrap. It refuses mutable
# references and executes only an approved release whose platform matches the
# provisioned gala. Platform migrations are never performed here.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
MANIFEST_PATH="${2:-}"
[[ -n "$CONFIG_PATH" && -n "$MANIFEST_PATH" ]] || fail "usage: $0 CONFIG RELEASE_MANIFEST"
load_gala_config "$CONFIG_PATH"
require_command aws
require_command docker
require_command python3
require_var AWS_REGION
require_var COMPOSE_FILES

"$SCRIPT_DIR/reclaim-deployment-space.sh" "$CONFIG_PATH"

# Hosts deployed before the first-backup gate may have a release marker but no
# backup. Take that backup before preflight; never waive the gate on a retry.
if [[ -f "$(deployed_manifest_path)" && ! -s "$(runtime_dir)/last-successful-backup" ]]; then
  "$SCRIPT_DIR/backup-postgres.sh" "$CONFIG_PATH"
fi

# Materialize the three app-specific secrets before Compose reads their env_file
# paths. This is also required for the first release, before systemd has ever
# started the stacks.
"$SCRIPT_DIR/fetch-runtime-secret.sh" "$CONFIG_PATH"
"$SCRIPT_DIR/preflight.sh" "$CONFIG_PATH" "$MANIFEST_PATH"

# preflight runs in a separate process. Load the same validated manifest again
# here so the images exported to Compose are exactly the release it checked.
load_release_images "$MANIFEST_PATH"
write_compose_environment

lespass_registry="${LESPASS_IMAGE%%/*}"
[[ "$lespass_registry" == *.dkr.ecr.*.amazonaws.com ]] || fail "LESPASS_IMAGE must use the Gala ECR registry"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$lespass_registry" >/dev/null

prepare_writable_mounts() {
  local image="$1" app_user="$2" path uid gid
  shift 2
  # The application images run unprivileged. Docker creates absent bind-mount
  # directories as root, so first boot must set ownership before Compose up.
  uid="$(docker run --rm --network none --user "$app_user" --entrypoint id "$image" -u)"
  gid="$(docker run --rm --network none --user "$app_user" --entrypoint id "$image" -g)"
  [[ "$uid" =~ ^[1-9][0-9]{0,5}$ && "$gid" =~ ^[1-9][0-9]{0,5}$ ]] \
    || fail "invalid non-root identity for $app_user image"
  for path in "$@"; do
    [[ "$path" == "$REPO_ROOT/deploy/"* && ! -L "$path" ]] \
      || fail "unsafe application bind mount path"
    install -d -m 0755 -o "$uid" -g "$gid" "$path"
    # Git may already contain nested static files, and an earlier failed boot
    # may have left root-owned children. Stay within these application-only
    # mounts; -h does not follow symlinks into unrelated host paths.
    chown -hR "$uid:$gid" "$path"
  done
}

IFS=':' read -r -a compose_groups <<< "$COMPOSE_FILES"
for group in "${compose_groups[@]}"; do
  compose_group_args "$group"
  # SSM truncates noisy stderr at 24 KB; keep the actual deployment error visible.
  docker compose --env-file "$(compose_env_file)" "${COMPOSE_ARGS[@]}" pull --quiet
done

prepare_writable_mounts "$FEDOW_IMAGE" fedow \
  "$REPO_ROOT/deploy/Fedow/www" "$REPO_ROOT/deploy/Fedow/logs"
prepare_writable_mounts "$LABOUTIK_IMAGE" tibillet \
  "$REPO_ROOT/deploy/Laboutik/www" "$REPO_ROOT/deploy/Laboutik/logs" \
  "$REPO_ROOT/deploy/Laboutik/backup"
prepare_writable_mounts "$LESPASS_IMAGE" tibillet \
  "$REPO_ROOT/deploy/Lespass/www" "$REPO_ROOT/deploy/Lespass/logs" \
  "$REPO_ROOT/deploy/Lespass/backup"

for group in "${compose_groups[@]}"; do
  compose_group_args "$group"
  app_service=""
  case "$group" in
    *"/deploy/Fedow/docker-compose.yml"*) app_service="fedow_django" ;;
    *"/deploy/Laboutik/docker-compose.yml"*) app_service="laboutik_django" ;;
  esac
  previous_id=""
  if [[ -n "$app_service" ]]; then
    previous_id="$(docker inspect --format '{{.Id}}' "$app_service" 2>/dev/null || true)"
  fi
  docker compose --env-file "$(compose_env_file)" "${COMPOSE_ARGS[@]}" up -d --remove-orphans
  # Fedow and Laboutik images can remain pinned while their versioned bind-
  # mounted code changes. Restart only an existing, reused app container; on a
  # fresh host Compose starts it once. Never restart its database for this.
  if [[ -n "$previous_id" ]]; then
    current_id="$(docker inspect --format '{{.Id}}' "$app_service")"
    if [[ "$previous_id" == "$current_id" ]]; then
      docker compose --env-file "$(compose_env_file)" "${COMPOSE_ARGS[@]}" restart "$app_service"
    fi
  fi
done

# The upstream Lespass image explicitly ships MIGRATE=0 and comments out its
# install command. A newly provisioned Gala therefore needs both steps in the
# reviewed release workflow before its public tenant can answer requests.
# The install command exits harmlessly when domains already exist. During this
# one-time local Fedow handshake only, DEBUG disables verification of Traefik's
# temporary self-signed certificate; the web process remains DEBUG=0.
timeout 600s docker exec lespass_django bash -lc \
  'cd /DjangoFiles && export PATH="/home/tibillet/.local/bin:$PATH" && poetry run python manage.py migrate_schemas --executor=multiprocessing'
timeout 600s docker exec -e DEBUG=1 lespass_django bash -lc \
  'cd /DjangoFiles && export PATH="/home/tibillet/.local/bin:$PATH" && poetry run python manage.py install'
timeout 120s docker exec lespass_django bash -lc \
  'cd /DjangoFiles && export PATH="/home/tibillet/.local/bin:$PATH" && poetry run python manage.py configure_gala_apex'

healthy=false
for attempt in {1..60}; do
  if "$SCRIPT_DIR/healthcheck.sh" "$CONFIG_PATH"; then
    healthy=true
    break
  fi
  if (( attempt < 60 )); then sleep 5; fi
done
[[ "$healthy" == true ]] || fail "local healthcheck did not pass after 60 attempts"
# A fresh Gala must have a recoverable database snapshot before its first
# release is marked deployed. Existing Galas are already covered by preflight.
if [[ ! -s "$(runtime_dir)/last-successful-backup" ]]; then
  "$SCRIPT_DIR/backup-postgres.sh" "$CONFIG_PATH"
fi
# Enable the periodic timer only after databases exist and one upload worked.
# install-runtime-contract intentionally does not start it during bootstrap.
systemctl enable --now "tibillet-gala-backup@${GALA_SLUG}.timer"
install -d -m 0750 "$(release_dir)"
manifest_copy="$(mktemp "$(release_dir)/deployed-manifest.json.XXXXXX")"
cleanup() { rm -f "$manifest_copy"; }
trap cleanup EXIT
cp "$MANIFEST_PATH" "$manifest_copy"
chmod 600 "$manifest_copy"
mv -f "$manifest_copy" "$(deployed_manifest_path)"
printf 'Deployment completed: gala=%s release=%s\n' "$GALA_SLUG" "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["release_id"])' "$MANIFEST_PATH")"
