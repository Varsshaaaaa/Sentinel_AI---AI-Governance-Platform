#!/usr/bin/env bash
# SentinelAI infrastructure — shared configuration and helpers

set -euo pipefail

_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$(cd "${_LIB_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Defaults (override via environment or infrastructure/.env)
export AWS_REGION="${AWS_REGION:-us-east-1}"
export PROJECT_NAME="${PROJECT_NAME:-sentinelai}"
export ENVIRONMENT="${ENVIRONMENT:-dev}"
export PREFIX="${PROJECT_NAME}-${ENVIRONMENT}"
export DYNAMODB_TABLE_PREFIX="${DYNAMODB_TABLE_PREFIX:-${PREFIX}}"
export EVENTBRIDGE_BUS_NAME="${EVENTBRIDGE_BUS_NAME:-${PREFIX}-governance}"
export LAMBDA_FUNCTION_NAME="${LAMBDA_FUNCTION_NAME:-${PREFIX}-api}"
export LAMBDA_WS_FUNCTION_NAME="${LAMBDA_WS_FUNCTION_NAME:-${PREFIX}-waf-ws}"
export LAMBDA_WS_HANDLER="${LAMBDA_WS_HANDLER:-lambda.ws_handler.handler}"
export WAF_WEBSOCKET_STAGE="${WAF_WEBSOCKET_STAGE:-prod}"
export WAF_WEBSOCKET_API_NAME="${WAF_WEBSOCKET_API_NAME:-${PREFIX}-waf-stream}"
export DEPLOY_WAF_WEBSOCKET="${DEPLOY_WAF_WEBSOCKET:-true}"
export LAMBDA_ROLE_NAME="${LAMBDA_ROLE_NAME:-${PREFIX}-lambda-role}"
export LAMBDA_RUNTIME="${LAMBDA_RUNTIME:-python3.11}"
export LAMBDA_HANDLER="${LAMBDA_HANDLER:-lambda.handler.handler}"
export LAMBDA_MEMORY="${LAMBDA_MEMORY:-512}"
export LAMBDA_TIMEOUT="${LAMBDA_TIMEOUT:-29}"

if [[ -f "${SCRIPT_DIR}/../.env" ]]; then
  # shellcheck disable=SC1091
  set -a && source "${SCRIPT_DIR}/../.env" && set +a
fi

log() { echo "[sentinelai] $*"; }
warn() { echo "[sentinelai][warn] $*" >&2; }
die() { echo "[sentinelai][error] $*" >&2; exit 1; }

require_aws() {
  command -v aws >/dev/null 2>&1 || die "AWS CLI not found. Install: https://aws.amazon.com/cli/"
  aws sts get-caller-identity >/dev/null 2>&1 || die "AWS credentials not configured. Run: aws configure"
}

table_exists() {
  local name="$1"
  aws dynamodb describe-table --table-name "$name" --region "$AWS_REGION" >/dev/null 2>&1
}

create_simple_table() {
  local name="$1"
  if table_exists "$name"; then
    log "DynamoDB table exists: $name"
    return 0
  fi
  log "Creating DynamoDB table: $name"
  aws dynamodb create-table \
    --table-name "$name" \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions \
      AttributeName=PK,AttributeType=S \
      AttributeName=SK,AttributeType=S \
    --key-schema \
      AttributeName=PK,KeyType=HASH \
      AttributeName=SK,KeyType=RANGE \
    --tags Key=Project,Value="$PROJECT_NAME" Key=Environment,Value="$ENVIRONMENT" \
    --region "$AWS_REGION" >/dev/null
  aws dynamodb wait table-exists --table-name "$name" --region "$AWS_REGION"
}

create_gsi1_table() {
  local name="$1"
  if table_exists "$name"; then
    log "DynamoDB table exists: $name"
    return 0
  fi
  log "Creating DynamoDB table (GSI1): $name"
  aws dynamodb create-table \
    --table-name "$name" \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions \
      AttributeName=PK,AttributeType=S \
      AttributeName=SK,AttributeType=S \
      AttributeName=GSI1PK,AttributeType=S \
      AttributeName=GSI1SK,AttributeType=S \
    --key-schema \
      AttributeName=PK,KeyType=HASH \
      AttributeName=SK,KeyType=RANGE \
    --global-secondary-indexes \
      "[{\"IndexName\":\"GSI1\",\"KeySchema\":[{\"AttributeName\":\"GSI1PK\",\"KeyType\":\"HASH\"},{\"AttributeName\":\"GSI1SK\",\"KeyType\":\"RANGE\"}],\"Projection\":{\"ProjectionType\":\"ALL\"}}]" \
    --tags Key=Project,Value="$PROJECT_NAME" Key=Environment,Value="$ENVIRONMENT" \
    --region "$AWS_REGION" >/dev/null
  aws dynamodb wait table-exists --table-name "$name" --region "$AWS_REGION"
}

create_graph_table() {
  local name="$1"
  if table_exists "$name"; then
    log "DynamoDB table exists: $name"
    return 0
  fi
  log "Creating DynamoDB graph table: $name"
  aws dynamodb create-table \
    --table-name "$name" \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions \
      AttributeName=PK,AttributeType=S \
      AttributeName=SK,AttributeType=S \
      AttributeName=GSI1PK,AttributeType=S \
      AttributeName=GSI1SK,AttributeType=S \
      AttributeName=GSI2PK,AttributeType=S \
      AttributeName=GSI2SK,AttributeType=S \
    --key-schema \
      AttributeName=PK,KeyType=HASH \
      AttributeName=SK,KeyType=RANGE \
    --global-secondary-indexes \
      "[{\"IndexName\":\"GSI1\",\"KeySchema\":[{\"AttributeName\":\"GSI1PK\",\"KeyType\":\"HASH\"},{\"AttributeName\":\"GSI1SK\",\"KeyType\":\"RANGE\"}],\"Projection\":{\"ProjectionType\":\"ALL\"}},{\"IndexName\":\"GSI2\",\"KeySchema\":[{\"AttributeName\":\"GSI2PK\",\"KeyType\":\"HASH\"},{\"AttributeName\":\"GSI2SK\",\"KeyType\":\"RANGE\"}],\"Projection\":{\"ProjectionType\":\"ALL\"}}]" \
    --tags Key=Project,Value="$PROJECT_NAME" Key=Environment,Value="$ENVIRONMENT" \
    --region "$AWS_REGION" >/dev/null
  aws dynamodb wait table-exists --table-name "$name" --region "$AWS_REGION"
}
