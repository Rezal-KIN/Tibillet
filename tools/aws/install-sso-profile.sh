#!/usr/bin/env bash
# Installs the portable Gala SSO profile block into ~/.aws/config on any
# computer. Never carries a long-lived key — only the public SSO start URL,
# region, and account ID needed to open a browser MFA login.
#
# Usage: tools/aws/install-sso-profile.sh
#
# The placeholders below are filled in once, by a human, after IAM Identity
# Center is enabled in the independent Gala AWS account (see
# docs/aws-access.md). This script refuses to run until they are.
set -euo pipefail

SSO_START_URL="https://d-80677e1879.awsapps.com/start"
SSO_REGION="eu-west-3"
GALA_ACCOUNT_ID="318629836660"
RUNTIME_REGION="eu-west-3"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for placeholder in SSO_START_URL SSO_REGION GALA_ACCOUNT_ID; do
  case "${!placeholder}" in
    __GALA_*__)
      fail "$placeholder is still a placeholder. Edit tools/aws/install-sso-profile.sh with the real value from docs/aws-access.md before running it."
      ;;
  esac
done

command -v aws >/dev/null 2>&1 || fail "AWS CLI v2 is required (https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)"

CONFIG_FILE="${AWS_CONFIG_FILE:-$HOME/.aws/config}"
MARKER_BEGIN="# BEGIN gala-sso-profile (managed by tools/aws/install-sso-profile.sh)"
MARKER_END="# END gala-sso-profile"

mkdir -p "$(dirname "$CONFIG_FILE")"
touch "$CONFIG_FILE"

if grep -qF "$MARKER_BEGIN" "$CONFIG_FILE" 2>/dev/null; then
  fail "$CONFIG_FILE already has a gala-sso-profile block. Remove the block between '$MARKER_BEGIN' and '$MARKER_END' first if you want to reinstall it."
fi

BLOCK=$(cat <<EOF

$MARKER_BEGIN
[sso-session gala]
sso_start_url = $SSO_START_URL
sso_region = $SSO_REGION
sso_registration_scopes = sso:account:access

[profile gala-operator]
sso_session = gala
sso_account_id = $GALA_ACCOUNT_ID
sso_role_name = Gala-Operator
region = $RUNTIME_REGION
output = json

[profile gala-elevated]
sso_session = gala
sso_account_id = $GALA_ACCOUNT_ID
sso_role_name = Gala-Elevated
region = $RUNTIME_REGION
output = json

[profile gala-administrator]
sso_session = gala
sso_account_id = $GALA_ACCOUNT_ID
sso_role_name = Gala-Administrator
region = $RUNTIME_REGION
output = json
$MARKER_END
EOF
)

printf '%s\n' "$BLOCK" >> "$CONFIG_FILE"

printf 'Installed gala-operator, gala-elevated, and gala-administrator profiles in %s\n' "$CONFIG_FILE"
printf 'Next: aws sso login --profile gala-operator\n'
