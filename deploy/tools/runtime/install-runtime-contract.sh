#!/usr/bin/env bash
# Reinstall versioned runtime scripts and systemd units from the pinned repo.
# This can run at first boot or again through SSM after a reviewed Git fetch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 CONFIG"
load_gala_config "$CONFIG_PATH"
require_var GENERATED_SECRET_ARN
require_var SHARED_STRIPE_SECRET_ARN
require_var SHARED_MAIL_SECRET_ARN
[[ -d "$REPO_ROOT/.git" ]] || fail "versioned Gala repository is missing"
require_command docker

docker network inspect frontend >/dev/null 2>&1 || docker network create frontend >/dev/null
acme_file="$REPO_ROOT/deploy/traefik/acme.json"
if [[ ! -e "$acme_file" ]]; then
  install -m 0600 /dev/null "$acme_file"
fi
[[ -f "$acme_file" && ! -L "$acme_file" ]] || fail "Traefik ACME storage must be a regular file"
chmod 0600 "$acme_file"

runtime_library="/usr/local/lib/tibillet-gala"
install -d -m 0755 "$runtime_library" /etc/tibillet-gala /var/lib/tibillet-gala
for script in \
  backup-postgres.sh deploy-release-from-s3.sh deploy-release.sh \
  fetch-runtime-secret.sh healthcheck.sh install-runtime-contract.sh lib.sh \
  materialize-runtime-env.py preflight.sh reclaim-deployment-space.sh restore-postgres.sh \
  verify-backup-restore.sh \
  start-stacks.sh stop-stacks.sh validate-release.py; do
  install -m 0755 "$REPO_ROOT/deploy/tools/runtime/$script" "$runtime_library/$script"
done

install -m 0644 "$REPO_ROOT/deploy/systemd/tibillet-gala-stacks.service" "/etc/systemd/system/tibillet-gala-stacks@.service"
install -m 0644 "$REPO_ROOT/deploy/systemd/tibillet-gala-backup.service" "/etc/systemd/system/tibillet-gala-backup@.service"
install -m 0644 "$REPO_ROOT/deploy/systemd/tibillet-gala-backup.timer" "/etc/systemd/system/tibillet-gala-backup@.timer"
systemctl daemon-reload
systemctl enable "tibillet-gala-stacks@${GALA_SLUG}.service"
printf 'Runtime contract installed for gala %s at commit %s\n' "$GALA_SLUG" "$(git -C "$REPO_ROOT" rev-parse HEAD)"
