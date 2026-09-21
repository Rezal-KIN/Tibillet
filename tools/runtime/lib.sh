#!/usr/bin/env bash
# Shared helpers for Gala runtime operations. The caller must source a root-owned
# gala configuration file; no operation prints its values.
set -euo pipefail

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

require_var() {
  local name="$1"
  [[ -n "${!name:-}" ]] || fail "required configuration is empty: $name"
}

require_safe_slug() {
  [[ "${GALA_SLUG:-}" =~ ^[a-z0-9][a-z0-9-]{1,62}$ ]] || fail "GALA_SLUG must be a lowercase slug"
}

load_gala_config() {
  local config_path="$1"
  [[ -f "$config_path" ]] || fail "gala config not found: $config_path"
  [[ ! -L "$config_path" ]] || fail "gala config must not be a symlink: $config_path"

  # shellcheck source=/dev/null
  source "$config_path"
  require_safe_slug
  require_var AWS_REGION
  require_var BACKUP_BUCKET
  require_var REPO_ROOT
}

runtime_dir() {
  printf '%s\n' "${RUNTIME_ROOT:-/var/lib/tibillet-gala}/${GALA_SLUG}"
}

# COMPOSE_FILES is a ':'-separated list of groups; each group is a ';'-separated
# list of compose files merged into ONE `docker compose` invocation (multiple
# `-f` flags). This is what lets a per-service docker-compose.release.yml
# override actually take effect instead of being invoked as an unrelated
# second project. Populates the global array COMPOSE_ARGS.
compose_group_args() {
  local group="$1"
  local file
  COMPOSE_ARGS=()
  IFS=';' read -r -a _compose_group_files <<< "$group"
  for file in "${_compose_group_files[@]}"; do
    [[ -f "$file" ]] || fail "compose file missing: $file"
    COMPOSE_ARGS+=(-f "$file")
  done
}

compose_env_file() {
  printf '%s\n' "$(runtime_dir)/compose.env"
}

deployed_manifest_path() {
  printf '%s\n' "$(release_dir)/deployed-manifest.json"
}

require_public_domain() {
  local name="$1"
  local value="${!name:-}"
  [[ "$value" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || fail "$name must be a lowercase hostname"
}

# The app dotenv files are separate because the apps legitimately have colliding
# keys such as DOMAIN and POSTGRES_DB. Release image values come only from a
# validated release manifest, so a reboot cannot fall back to latest or a build.
load_release_images() {
  local manifest_path="$1"
  local manifest_platform
  [[ -f "$manifest_path" ]] || fail "deployed release manifest is missing: $manifest_path"
  require_command python3
  "$(dirname "${BASH_SOURCE[0]}")/validate-release.py" "$manifest_path" >/dev/null

  manifest_platform="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["platform"])' "$manifest_path")"
  [[ "$manifest_platform" == "$PLATFORM" ]] || fail "deployed release platform does not match runtime configuration"
  LESPASS_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["lespass_image"])' "$manifest_path")"
  FEDOW_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fedow_image"])' "$manifest_path")"
  LABOUTIK_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["laboutik_image"])' "$manifest_path")"
  TRAEFIK_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["traefik_image"])' "$manifest_path")"
  export LESPASS_IMAGE FEDOW_IMAGE LABOUTIK_IMAGE TRAEFIK_IMAGE
}

# Compose uses this separate non-secret dotenv only for interpolation. The
# actual runtime secrets live in three app-specific dotenv files because the
# apps legitimately have colliding keys such as DOMAIN and POSTGRES_DB.
# The exact release images are persisted here after a healthy deployment so a
# reboot can never fall back to latest or a local build.
write_compose_environment() {
  require_public_domain FEDOW_PUBLIC_DOMAIN
  require_public_domain LABOUTIK_PUBLIC_DOMAIN
  require_public_domain LESPASS_PUBLIC_DOMAIN
  require_var FEDOW_IMAGE
  require_var LABOUTIK_IMAGE
  require_var LESPASS_IMAGE
  require_var TRAEFIK_IMAGE

  local env_file
  local tmp_file
  env_file="$(compose_env_file)"
  mkdir -p "$(runtime_dir)"
  umask 077
  tmp_file="$(mktemp "$(runtime_dir)/compose.env.XXXXXX")"
  printf '%s\n' \
    "FEDOW_RUNTIME_ENV_FILE=$(runtime_dir)/fedow.env" \
    "LABOUTIK_RUNTIME_ENV_FILE=$(runtime_dir)/laboutik.env" \
    "LESPASS_RUNTIME_ENV_FILE=$(runtime_dir)/lespass.env" \
    "FEDOW_PUBLIC_DOMAIN=$FEDOW_PUBLIC_DOMAIN" \
    "LABOUTIK_PUBLIC_DOMAIN=$LABOUTIK_PUBLIC_DOMAIN" \
    "LESPASS_PUBLIC_DOMAIN=$LESPASS_PUBLIC_DOMAIN" \
    "FEDOW_IMAGE=$FEDOW_IMAGE" \
    "LABOUTIK_IMAGE=$LABOUTIK_IMAGE" \
    "LESPASS_IMAGE=$LESPASS_IMAGE" \
    "TRAEFIK_IMAGE=$TRAEFIK_IMAGE" > "$tmp_file"
  chmod 600 "$tmp_file"
  mv -f "$tmp_file" "$env_file"
}

release_dir() {
  printf '%s\n' "$(runtime_dir)/releases"
}

utc_timestamp() {
  date -u +%Y%m%dT%H%M%SZ
}
