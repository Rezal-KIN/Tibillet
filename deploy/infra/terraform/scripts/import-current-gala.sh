#!/usr/bin/env bash
# Prints import commands only. It makes no AWS call and has no defaults because
# the current resources must be identified through an SSO read-only inventory.
set -euo pipefail

: "${GALA_SLUG:?Set GALA_SLUG after inventory}"
: "${INSTANCE_ID:?Set INSTANCE_ID after inventory}"
: "${EIP_ALLOCATION_ID:?Set EIP_ALLOCATION_ID after inventory}"
: "${SECURITY_GROUP_ID:?Set SECURITY_GROUP_ID after inventory}"

cat <<COMMANDS
# Run each command only after `terraform plan` has been reviewed.
terraform import 'module.gala["${GALA_SLUG}"].aws_instance.runtime[0]' '${INSTANCE_ID}'
terraform import 'module.gala["${GALA_SLUG}"].aws_eip.runtime[0]' '${EIP_ALLOCATION_ID}'
terraform import 'module.gala["${GALA_SLUG}"].aws_security_group.runtime' '${SECURITY_GROUP_ID}'
COMMANDS
