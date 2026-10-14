#!/usr/bin/env bash
# Read one dev/prod secret. Legacy reads remain available during migration.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 CONFIG"
load_gala_config "$CONFIG_PATH"
mode_args=()
if [[ "${2:-}" == "--check-combined-compatibility" ]]; then
  mode_args+=(--check-combined-compatibility)
elif [[ -n "${2:-}" ]]; then
  fail "unsupported runtime secret mode"
fi
require_command aws
require_command python3
require_var GENERATED_SECRET_ARN
require_var SHARED_STRIPE_SECRET_ARN
require_var SHARED_MAIL_SECRET_ARN
require_var FEDOW_PUBLIC_DOMAIN
require_var LABOUTIK_PUBLIC_DOMAIN
require_var LESPASS_PUBLIC_DOMAIN

umask 077
mkdir -p "$(runtime_dir)"
generated_file="$(mktemp "$(runtime_dir)/generated-secret.XXXXXX")"
stripe_file="$(mktemp "$(runtime_dir)/shared-stripe.XXXXXX")"
mail_file="$(mktemp "$(runtime_dir)/shared-mail.XXXXXX")"
admin_file="$(mktemp "$(runtime_dir)/shared-admin.XXXXXX")"
cleanup() { rm -f "$generated_file" "$stripe_file" "$mail_file" "$admin_file"; }
trap cleanup EXIT

aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$SHARED_STRIPE_SECRET_ARN" \
  --query SecretString \
  --output text > "$stripe_file"
schema_version="$(python3 - "$stripe_file" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))['schema_version'])
PY
)"
secret_args=()
if [[ "$schema_version" == "2" ]]; then
  secret_args+=(--environment "$stripe_file" --gala-slug "$GALA_SLUG")
else
aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$GENERATED_SECRET_ARN" \
  --query SecretString \
  --output text > "$generated_file"
aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$SHARED_MAIL_SECRET_ARN" \
  --query SecretString \
  --output text > "$mail_file"

# A dedicated version stage preserves the AWSCURRENT mail schema used by
# older releases. No new secret or additional runtime IAM grant is required.
aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$SHARED_MAIL_SECRET_ARN" \
  --version-stage GALA_ADMIN \
  --query SecretString \
  --output text > "$admin_file"
secret_args+=(--generated "$generated_file" --stripe "$stripe_file" --mail "$mail_file" --admin "$admin_file")
fi

python3 "$SCRIPT_DIR/materialize-runtime-env.py" \
  "${secret_args[@]}" \
  --provider "${PAYMENT_PROVIDER:-stripe}" "${mode_args[@]}" \
  --smoke "$([[ "$GALA_SLUG" == "gala-smoke" || "$GALA_SLUG" == "gala-smoke-cawl" ]] && printf true || printf false)" \
  --fedow-domain "$FEDOW_PUBLIC_DOMAIN" \
  --laboutik-domain "$LABOUTIK_PUBLIC_DOMAIN" \
  --lespass-domain "$LESPASS_PUBLIC_DOMAIN" \
  --output-dir "$(runtime_dir)"

[[ ${#mode_args[@]} -gt 0 ]] || printf 'Runtime credentials materialized for gala %s\n' "$GALA_SLUG"
