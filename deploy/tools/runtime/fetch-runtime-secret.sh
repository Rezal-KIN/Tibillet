#!/usr/bin/env bash
# Fetch the one Gala runtime secret and atomically materialize its three
# application-specific dotenv files.  Secret values are never printed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
[[ -n "$CONFIG_PATH" ]] || fail "usage: $0 CONFIG"
load_gala_config "$CONFIG_PATH"
require_command aws
require_command python3
require_var RUNTIME_SECRET_ARN

secret_json="$(aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$RUNTIME_SECRET_ARN" \
  --query SecretString \
  --output text)"

umask 077
mkdir -p "$(runtime_dir)"
secret_file="$(mktemp "$(runtime_dir)/runtime-secret.XXXXXX")"
cleanup() { rm -f "$secret_file"; }
trap cleanup EXIT
printf '%s' "$secret_json" > "$secret_file"
chmod 600 "$secret_file"

python3 - "$(runtime_dir)" "$secret_file" <<'PY'
import json
import os
import sys
import tempfile

runtime_dir = sys.argv[1]
secret_file = sys.argv[2]
required = {
    "fedow_env": "fedow.env",
    "laboutik_env": "laboutik.env",
    "lespass_env": "lespass.env",
}

try:
    with open(secret_file, encoding="utf-8") as source:
        payload = json.load(source)
except json.JSONDecodeError as exc:
    raise SystemExit(f"runtime secret is not valid JSON: {exc.msg}") from exc

if not isinstance(payload, dict) or set(payload) != set(required):
    raise SystemExit("runtime secret must contain exactly fedow_env, laboutik_env, and lespass_env")

for key, filename in required.items():
    value = payload[key]
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SystemExit(f"runtime secret field {key} must be a non-empty text dotenv payload")

    descriptor, temporary_path = tempfile.mkstemp(prefix=f".{filename}.", dir=runtime_dir, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(value)
            if not value.endswith("\n"):
                temporary_file.write("\n")
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, os.path.join(runtime_dir, filename))
    except BaseException:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise
PY

printf 'Runtime secret materialized for gala %s\n' "$GALA_SLUG"
