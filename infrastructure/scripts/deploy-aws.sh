#!/usr/bin/env bash
# Full AWS infrastructure deploy for SentinelAI

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

log "Deploying SentinelAI to AWS (region: ${AWS_REGION}, env: ${ENVIRONMENT})"

bash "${SCRIPT_DIR}/create-dynamodb-tables.sh"
bash "${SCRIPT_DIR}/create-eventbridge.sh"

if [[ "${DEPLOY_LAMBDA:-false}" == "true" ]]; then
  bash "${SCRIPT_DIR}/package-lambda.sh"
  bash "${SCRIPT_DIR}/deploy-lambda.sh"
  if [[ "${DEPLOY_WAF_WEBSOCKET:-true}" == "true" ]]; then
    bash "${SCRIPT_DIR}/create-websocket-api.sh"
    BUILD_OUT="${PROJECT_ROOT}/infrastructure/build/waf-websocket.env"
    if [[ -f "$BUILD_OUT" ]]; then
      # shellcheck disable=SC1090
      source "$BUILD_OUT"
      log "Updating REST Lambda with WAF WebSocket management endpoint"
      aws lambda update-function-configuration \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --environment "Variables={ENVIRONMENT=${ENVIRONMENT},STORAGE_BACKEND=dynamodb,DYNAMODB_TABLE_PREFIX=${DYNAMODB_TABLE_PREFIX},EVENTBRIDGE_BUS_NAME=${EVENTBRIDGE_BUS_NAME},LOG_LEVEL=INFO,WAF_WEBSOCKET_API_ENDPOINT=${WAF_WEBSOCKET_API_ENDPOINT},AWS_REGION=${AWS_REGION}}" \
        --region "$AWS_REGION" >/dev/null 2>&1 || warn "Could not update REST Lambda WebSocket env (deploy REST Lambda first)"
    fi
  fi
else
  warn "Skipping Lambda deploy. Set DEPLOY_LAMBDA=true and LAMBDA_ROLE_ARN to deploy API."
fi

log "Deploy complete."
log "  DynamoDB prefix: ${DYNAMODB_TABLE_PREFIX}"
log "  EventBridge bus: ${EVENTBRIDGE_BUS_NAME}"
log ""
log "Next steps:"
log "  1. Set STORAGE_BACKEND=dynamodb in your runtime environment"
log "  2. Run locally against AWS: STORAGE_BACKEND=dynamodb make dev"
log "  3. Optional Lambda: DEPLOY_LAMBDA=true LAMBDA_ROLE_ARN=arn:... bash infrastructure/scripts/deploy-aws.sh"
