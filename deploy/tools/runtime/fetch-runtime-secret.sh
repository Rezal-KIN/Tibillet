#!/usr/bin/env bash
# Assemble stable per-Gala credentials and shared Stripe/mail credentials
# into three application-specific dotenv files. Secret values are never printed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 CONFIG"
load_gala_config "$CONFIG_PATH"
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
cleanup() { rm -f "$generated_file" "$stripe_file" "$mail_file"; }
trap cleanup EXIT

aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$GENERATED_SECRET_ARN" \
  --query SecretString \
  --output text > "$generated_file"
aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$SHARED_STRIPE_SECRET_ARN" \
  --query SecretString \
  --output text > "$stripe_file"
aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$SHARED_MAIL_SECRET_ARN" \
  --query SecretString \
  --output text > "$mail_file"

python3 "$SCRIPT_DIR/materialize-runtime-env.py" \
  --generated "$generated_file" \
  --stripe "$stripe_file" \
  --mail "$mail_file" \
  --smoke "$([[ "$GALA_SLUG" == "gala-smoke" ]] && printf true || printf false)" \
  --fedow-domain "$FEDOW_PUBLIC_DOMAIN" \
  --laboutik-domain "$LABOUTIK_PUBLIC_DOMAIN" \
  --lespass-domain "$LESPASS_PUBLIC_DOMAIN" \
  --output-dir "$(runtime_dir)"

printf 'Runtime credentials materialized for gala %s\n' "$GALA_SLUG"
