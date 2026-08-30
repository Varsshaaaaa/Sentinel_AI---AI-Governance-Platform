#!/usr/bin/env bash
# Tear down SentinelAI AWS resources (DynamoDB tables + EventBridge bus)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

require_aws

if [[ "${CONFIRM_DESTROY:-}" != "yes" ]]; then
  die "Refusing to destroy without CONFIRM_DESTROY=yes"
fi

PREFIX="${DYNAMODB_TABLE_PREFIX}"
TABLES=(
  "${PREFIX}-agents"
  "${PREFIX}-policies"
  "${PREFIX}-violations"
  "${PREFIX}-audit"
  "${PREFIX}-graph"
  "${PREFIX}-events"
  "${PREFIX}-governance"
  "${PREFIX}-websocket"
)

for table in "${TABLES[@]}"; do
  if table_exists "$table"; then
    log "Deleting DynamoDB table: $table"
    aws dynamodb delete-table --table-name "$table" --region "$AWS_REGION" >/dev/null
  fi
done

BUS="${EVENTBRIDGE_BUS_NAME}"
if aws events describe-event-bus --name "$BUS" --region "$AWS_REGION" >/dev/null 2>&1; then
  log "Deleting EventBridge bus: $BUS"
  aws events delete-event-bus --name "$BUS" --region "$AWS_REGION" >/dev/null
fi

FN="${LAMBDA_FUNCTION_NAME}"
if [[ "${DELETE_LAMBDA:-false}" == "true" ]]; then
  if aws lambda get-function --function-name "$FN" --region "$AWS_REGION" >/dev/null 2>&1; then
    log "Deleting Lambda function: $FN"
    aws lambda delete-function --function-name "$FN" --region "$AWS_REGION" >/dev/null
  fi
fi

log "Destroy complete."
