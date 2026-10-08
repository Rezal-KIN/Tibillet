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
source_hosting=()
# Smoke can validate a candidate before its public Release is prepared. Every
# production release requires its exact source assets on GitHub first.
if [[ "$GALA_SLUG" != "gala-smoke" ]]; then
  source_hosting+=(--github-release)
fi
python3 "$REPO_ROOT/deploy/tools/build-source-offer.py" \
  --repository "$REPO_ROOT" --manifest "$MANIFEST_PATH" \
  --catalog "$REPO_ROOT/deploy/source/image-sources.json" \
  --output "$REPO_ROOT/deploy/source/public" --cache "$REPO_ROOT/deploy/source/cache" \
  --index-output "$REPO_ROOT/deploy/source/next-index.html" --verify-working-tree "${source_hosting[@]}"
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
python3 "$SCRIPT_DIR/validate-application-images.py" "$MANIFEST_PATH"

prepare_writable_mounts "$FEDOW_IMAGE" fedow \
  "$REPO_ROOT/deploy/Fedow/www" "$REPO_ROOT/deploy/Fedow/logs" \
  "$REPO_ROOT/deploy/Fedow/sqlite-database"
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
  docker compose --env-file "$(compose_env_file)" "${COMPOSE_ARGS[@]}" up -d --no-build --remove-orphans
  # Reload configuration only for an existing reused application container;
  # on a fresh host Compose starts it once. Never restart its database here.
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
# The multiprocessing executor can leave its workers waiting on the parent
# pipe after every schema reports "No migrations to apply". Use django-tenants'
# standard sequential executor so completion is deterministic on repeated
# releases as well as first boot.
timeout 900s docker exec lespass_django bash -lc \
  'cd /DjangoFiles && export PATH="/home/tibillet/.local/bin:$PATH" && poetry run python manage.py migrate_schemas'
timeout 600s docker exec -e DEBUG=1 lespass_django bash -lc \
  'cd /DjangoFiles && export PATH="/home/tibillet/.local/bin:$PATH" && poetry run python manage.py install'
timeout 120s docker exec lespass_django bash -lc \
  'cd /DjangoFiles && export PATH="/home/tibillet/.local/bin:$PATH" && poetry run python manage.py configure_gala_apex'

# Fedow retains the hostname recorded before the apex was reassigned. Its
# native Stripe return URL and webhooks must use the same canonical domain.
python3 "$SCRIPT_DIR/configure-gala-refill-domain.py" --domain "$LESPASS_PUBLIC_DOMAIN"

# The upstream Laboutik entrypoint attempts install before Lespass is ready
# and keeps serving HTTP even if that command fails. Re-run it after Lespass
# initialization against this Gala's local Traefik. DEBUG=1 applies only to
# this one-time command so it accepts the inactive Gala's temporary cert;
# the web process remains DEBUG=0. install exits when already populated.
timeout 600s docker exec -e DEBUG=1 laboutik_django bash -lc \
  'cd /DjangoFiles && export PATH="/home/tibillet/.local/bin:$PATH" && poetry run python manage.py install'

# Secrets Manager populates Fedow's env_file, but live Stripe requests and
# webhook verification read encrypted Configuration fields. Reconcile both
# keys on every release (first boot and rotation) before reporting health.
timeout 120s docker exec -i fedow_django sh -lc \
  'cd /home/fedow/Fedow && poetry run python manage.py shell' \
  < "$SCRIPT_DIR/reconcile-fedow-webhook.py"

# Fedow's cashless checkout is separate from Lespass ticket payouts. Without
# this explicit, idempotent setting, a Gala without Stripe Connect has a
# working QR flow but hides its "Recharge" action from card holders.
timeout 120s docker exec -w /DjangoFiles lespass_django \
  /home/tibillet/.local/bin/poetry run python manage.py configure_gala_refill

# Reuse the existing bootstrap accounts in all three databases. Credentials
# come from Secrets Manager; only a Django hash reaches the configuration tool.
python3 "$SCRIPT_DIR/configure-gala-admin.py" --gala "$GALA_SLUG" \
  --credentials-file "$(runtime_dir)/admin.json" --apply

# Import physical identities with the unchanged native Fedow command after
# pairing. CSVs and wrapper input are temporary; no new application bind mount.
python3 "$SCRIPT_DIR/import-gala-card-stock.py" "$MANIFEST_PATH" \
  --bucket "${RELEASE_BUCKET:-${BACKUP_BUCKET}}" --region "$AWS_REGION" \
  --domain "$LESPASS_PUBLIC_DOMAIN"

healthy=false
for attempt in {1..60}; do
  if "$SCRIPT_DIR/healthcheck.sh" "$CONFIG_PATH"; then
    healthy=true
    break
  fi
  if (( attempt < 60 )); then sleep 5; fi
done
[[ "$healthy" == true ]] || fail "local healthcheck did not pass after 60 attempts"
# Only advertise the new sources after the running apps pass their healthcheck.
# Previous source archives remain at their immutable URLs.
source_index="$(mktemp "$REPO_ROOT/deploy/source/public/.index.XXXXXX")"
install -m 0644 "$REPO_ROOT/deploy/source/next-index.html" "$source_index"
mv -f "$source_index" "$REPO_ROOT/deploy/source/public/index.html"
for domain in "$LESPASS_PUBLIC_DOMAIN" "$FEDOW_PUBLIC_DOMAIN" "$LABOUTIK_PUBLIC_DOMAIN"; do
  source_status="$(curl --fail --silent --show-error --insecure --noproxy '*' \
    --resolve "$domain:443:127.0.0.1" --max-time 20 \
    --output /dev/null --write-out '%{http_code}' "https://$domain/source/")"
  [[ "$source_status" == 200 ]] || fail "source offer is unavailable or redirects on $domain"
done
# A fresh Gala must have a recoverable database snapshot before its first
# release is marked deployed. Existing Galas are already covered by preflight.
fedow_storage_state="$(python3 "$SCRIPT_DIR/fedow-sqlite.py" initialize-storage "$REPO_ROOT" "$(runtime_dir)" --check-only)"
# Take a first SQLite backup even if a historical PostgreSQL backup exists.
if [[ "$fedow_storage_state" == initialized || ! -s "$(runtime_dir)/last-successful-backup" ]]; then
  "$SCRIPT_DIR/backup-postgres.sh" "$CONFIG_PATH"
fi
# Seal only after that upload succeeded; a failed first backup must be retried.
python3 "$SCRIPT_DIR/fedow-sqlite.py" initialize-storage "$REPO_ROOT" "$(runtime_dir)" >/dev/null
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
