#!/usr/bin/env bash
# Deploy or update SentinelAI Lambda function

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

require_aws

ZIP_FILE="${PROJECT_ROOT}/infrastructure/build/sentinelai-lambda.zip"
[[ -f "$ZIP_FILE" ]] || die "Run package-lambda.sh first"

FN="${LAMBDA_FUNCTION_NAME}"
ROLE_ARN="${LAMBDA_ROLE_ARN:-}"

if [[ -z "$ROLE_ARN" ]]; then
  die "Set LAMBDA_ROLE_ARN to an IAM role with DynamoDB, EventBridge, and CloudWatch Logs permissions"
fi

ENV_VARS="Variables={ENVIRONMENT=${ENVIRONMENT},STORAGE_BACKEND=dynamodb,DYNAMODB_TABLE_PREFIX=${DYNAMODB_TABLE_PREFIX},EVENTBRIDGE_BUS_NAME=${EVENTBRIDGE_BUS_NAME},LOG_LEVEL=INFO,AWS_REGION=${AWS_REGION}"
if [[ -n "${WAF_WEBSOCKET_API_ENDPOINT:-}" ]]; then
  ENV_VARS="Variables={ENVIRONMENT=${ENVIRONMENT},STORAGE_BACKEND=dynamodb,DYNAMODB_TABLE_PREFIX=${DYNAMODB_TABLE_PREFIX},EVENTBRIDGE_BUS_NAME=${EVENTBRIDGE_BUS_NAME},LOG_LEVEL=INFO,AWS_REGION=${AWS_REGION},WAF_WEBSOCKET_API_ENDPOINT=${WAF_WEBSOCKET_API_ENDPOINT}}"
fi

if aws lambda get-function --function-name "$FN" --region "$AWS_REGION" >/dev/null 2>&1; then
  log "Updating Lambda function: $FN"
  aws lambda update-function-code \
    --function-name "$FN" \
    --zip-file "fileb://${ZIP_FILE}" \
    --region "$AWS_REGION" >/dev/null
  aws lambda update-function-configuration \
    --function-name "$FN" \
    --handler "$LAMBDA_HANDLER" \
    --runtime "$LAMBDA_RUNTIME" \
    --memory-size "$LAMBDA_MEMORY" \
    --timeout "$LAMBDA_TIMEOUT" \
    --environment "$ENV_VARS" \
    --region "$AWS_REGION" >/dev/null
else
  log "Creating Lambda function: $FN"
  aws lambda create-function \
    --function-name "$FN" \
    --runtime "$LAMBDA_RUNTIME" \
    --role "$ROLE_ARN" \
    --handler "$LAMBDA_HANDLER" \
    --zip-file "fileb://${ZIP_FILE}" \
    --memory-size "$LAMBDA_MEMORY" \
    --timeout "$LAMBDA_TIMEOUT" \
    --environment "$ENV_VARS" \
    --tags Project="$PROJECT_NAME",Environment="$ENVIRONMENT" \
    --region "$AWS_REGION" >/dev/null
fi

log "Lambda deployed: $FN"
