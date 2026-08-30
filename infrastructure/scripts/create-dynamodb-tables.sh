#!/usr/bin/env bash
# Create all SentinelAI DynamoDB tables

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

require_aws

PREFIX="${DYNAMODB_TABLE_PREFIX}"

create_simple_table "${PREFIX}-agents"
create_simple_table "${PREFIX}-policies"
create_gsi1_table "${PREFIX}-violations"
create_simple_table "${PREFIX}-audit"
create_graph_table "${PREFIX}-graph"
create_gsi1_table "${PREFIX}-events"
create_simple_table "${PREFIX}-governance"
create_simple_table "${PREFIX}-websocket"

log "All DynamoDB tables ready (prefix: ${PREFIX})"
