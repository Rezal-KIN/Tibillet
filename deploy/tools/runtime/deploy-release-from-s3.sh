#!/usr/bin/env bash
# SSM entrypoint: accepts only an S3 URI under the target Gala release prefix.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CONFIG_PATH="${1:-}"
RELEASE_URI="${2:-}"
[[ -n "$CONFIG_PATH" && -n "$RELEASE_URI" ]] || fail "usage: $0 CONFIG s3://bucket/releases/<slug>/manifest.json"
load_gala_config "$CONFIG_PATH"
require_command aws

expected_prefix="s3://${RELEASE_BUCKET:-${BACKUP_BUCKET}}/releases/${GALA_SLUG}/"
[[ "$RELEASE_URI" == "$expected_prefix"* ]] || fail "release manifest is outside the Gala-only release prefix"
mkdir -p "$(release_dir)"
local_manifest="$(release_dir)/$(basename "$RELEASE_URI")"
aws s3 cp --only-show-errors "$RELEASE_URI" "$local_manifest"
"$SCRIPT_DIR/deploy-release.sh" "$CONFIG_PATH" "$local_manifest"
