#!/usr/bin/env bash
# Create EventBridge custom bus for governance events

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

require_aws

BUS="${EVENTBRIDGE_BUS_NAME}"

if aws events describe-event-bus --name "$BUS" --region "$AWS_REGION" >/dev/null 2>&1; then
  log "EventBridge bus exists: $BUS"
else
  log "Creating EventBridge bus: $BUS"
  aws events create-event-bus --name "$BUS" --region "$AWS_REGION" >/dev/null
fi

log "EventBridge bus ready: $BUS"
