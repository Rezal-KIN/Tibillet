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

IFS=':' read -r -a compose_groups <<< "$COMPOSE_FILES"
for group in "${compose_groups[@]}"; do
  compose_group_args "$group"
  docker compose --env-file "$(compose_env_file)" "${COMPOSE_ARGS[@]}" pull
  docker compose --env-file "$(compose_env_file)" "${COMPOSE_ARGS[@]}" up -d --remove-orphans
done

"$SCRIPT_DIR/healthcheck.sh" "$CONFIG_PATH"
install -d -m 0750 "$(release_dir)"
manifest_copy="$(mktemp "$(release_dir)/deployed-manifest.json.XXXXXX")"
cleanup() { rm -f "$manifest_copy"; }
trap cleanup EXIT
cp "$MANIFEST_PATH" "$manifest_copy"
chmod 600 "$manifest_copy"
mv -f "$manifest_copy" "$(deployed_manifest_path)"
printf 'Deployment completed: gala=%s release=%s\n' "$GALA_SLUG" "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["release_id"])' "$MANIFEST_PATH")"
