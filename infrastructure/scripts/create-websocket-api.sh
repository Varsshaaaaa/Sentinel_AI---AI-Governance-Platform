#!/usr/bin/env bash
# Create AWS API Gateway WebSocket API for WAF live dashboard (PS-5.1)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

require_aws

ROLE_ARN="${LAMBDA_ROLE_ARN:-}"
[[ -n "$ROLE_ARN" ]] || die "Set LAMBDA_ROLE_ARN for WebSocket Lambda deployment"

ZIP_FILE="${PROJECT_ROOT}/infrastructure/build/sentinelai-lambda.zip"
[[ -f "$ZIP_FILE" ]] || bash "${SCRIPT_DIR}/package-lambda.sh"

FN="${LAMBDA_WS_FUNCTION_NAME:-${PREFIX}-waf-ws}"
WS_HANDLER="${LAMBDA_WS_HANDLER:-lambda.ws_handler.handler}"
STAGE="${WAF_WEBSOCKET_STAGE:-prod}"
API_NAME="${WAF_WEBSOCKET_API_NAME:-${PREFIX}-waf-stream}"
BUILD_OUT="${PROJECT_ROOT}/infrastructure/build/waf-websocket.env"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ENV_VARS="Variables={ENVIRONMENT=${ENVIRONMENT},STORAGE_BACKEND=dynamodb,DYNAMODB_TABLE_PREFIX=${DYNAMODB_TABLE_PREFIX},AWS_REGION=${AWS_REGION},LOG_LEVEL=INFO}"

log "Deploying WAF WebSocket Lambda: $FN"
if aws lambda get-function --function-name "$FN" --region "$AWS_REGION" >/dev/null 2>&1; then
  aws lambda update-function-code \
    --function-name "$FN" \
    --zip-file "fileb://${ZIP_FILE}" \
    --region "$AWS_REGION" >/dev/null
  aws lambda update-function-configuration \
    --function-name "$FN" \
    --handler "$WS_HANDLER" \
    --runtime "$LAMBDA_RUNTIME" \
    --memory-size 256 \
    --timeout 29 \
    --environment "$ENV_VARS" \
    --region "$AWS_REGION" >/dev/null
else
  aws lambda create-function \
    --function-name "$FN" \
    --runtime "$LAMBDA_RUNTIME" \
    --role "$ROLE_ARN" \
    --handler "$WS_HANDLER" \
    --zip-file "fileb://${ZIP_FILE}" \
    --memory-size 256 \
    --timeout 29 \
    --environment "$ENV_VARS" \
    --tags Project="$PROJECT_NAME",Environment="$ENVIRONMENT" \
    --region "$AWS_REGION" >/dev/null
fi

LAMBDA_ARN="$(aws lambda get-function --function-name "$FN" --region "$AWS_REGION" --query 'Configuration.FunctionArn' --output text)"

API_ID="$(aws apigatewayv2 get-apis --region "$AWS_REGION" --query "Items[?Name=='${API_NAME}'].ApiId | [0]" --output text)"
if [[ -z "$API_ID" || "$API_ID" == "None" ]]; then
  log "Creating WebSocket API: $API_NAME"
  API_ID="$(aws apigatewayv2 create-api \
    --name "$API_NAME" \
    --protocol-type WEBSOCKET \
    --route-selection-expression '$request.body.action' \
    --region "$AWS_REGION" \
    --query ApiId --output text)"
else
  log "WebSocket API exists: $API_NAME ($API_ID)"
fi

INTEGRATION_URI="arn:aws:apigateway:${AWS_REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations"
INTEGRATION_ID="$(aws apigatewayv2 get-integrations --api-id "$API_ID" --region "$AWS_REGION" --query 'Items[0].IntegrationId' --output text 2>/dev/null || true)"
if [[ -z "$INTEGRATION_ID" || "$INTEGRATION_ID" == "None" ]]; then
  INTEGRATION_ID="$(aws apigatewayv2 create-integration \
    --api-id "$API_ID" \
    --integration-type AWS_PROXY \
    --integration-uri "$INTEGRATION_URI" \
    --region "$AWS_REGION" \
    --query IntegrationId --output text)"
fi

for ROUTE in '$connect' '$disconnect' '$default'; do
  EXISTING="$(aws apigatewayv2 get-routes --api-id "$API_ID" --region "$AWS_REGION" --query "Items[?RouteKey=='${ROUTE}'].RouteId | [0]" --output text)"
  if [[ -z "$EXISTING" || "$EXISTING" == "None" ]]; then
    aws apigatewayv2 create-route \
      --api-id "$API_ID" \
      --route-key "$ROUTE" \
      --target "integrations/${INTEGRATION_ID}" \
      --region "$AWS_REGION" >/dev/null
  fi
done

if ! aws apigatewayv2 get-stage --api-id "$API_ID" --stage-name "$STAGE" --region "$AWS_REGION" >/dev/null 2>&1; then
  aws apigatewayv2 create-stage \
    --api-id "$API_ID" \
    --stage-name "$STAGE" \
    --auto-deploy \
    --region "$AWS_REGION" >/dev/null
fi

STATEMENT_ID="apigateway-ws-${API_ID}"
aws lambda remove-permission \
  --function-name "$FN" \
  --statement-id "$STATEMENT_ID" \
  --region "$AWS_REGION" >/dev/null 2>&1 || true
aws lambda add-permission \
  --function-name "$FN" \
  --statement-id "$STATEMENT_ID" \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:${AWS_REGION}:${ACCOUNT_ID}:${API_ID}/*" \
  --region "$AWS_REGION" >/dev/null

WAF_WEBSOCKET_URL="wss://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/${STAGE}"
WAF_WEBSOCKET_API_ENDPOINT="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/${STAGE}"

mkdir -p "$(dirname "$BUILD_OUT")"
cat > "$BUILD_OUT" <<EOF
WAF_WEBSOCKET_URL=${WAF_WEBSOCKET_URL}
WAF_WEBSOCKET_API_ENDPOINT=${WAF_WEBSOCKET_API_ENDPOINT}
WAF_WEBSOCKET_API_ID=${API_ID}
LAMBDA_WS_FUNCTION_NAME=${FN}
EOF

log "WAF WebSocket deployed"
log "  Client URL (wss): ${WAF_WEBSOCKET_URL}"
log "  Management API:   ${WAF_WEBSOCKET_API_ENDPOINT}"
log "  Saved to: ${BUILD_OUT}"
log ""
log "Set on REST Lambda / backend:"
log "  WAF_WEBSOCKET_API_ENDPOINT=${WAF_WEBSOCKET_API_ENDPOINT}"
log "Set on frontend:"
log "  VITE_WAF_WEBSOCKET_URL=${WAF_WEBSOCKET_URL}"
