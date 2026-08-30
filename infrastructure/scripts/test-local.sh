#!/usr/bin/env bash
# Local smoke test — hits all major SentinelAI endpoints
# Usage: bash infrastructure/scripts/test-local.sh [base_url]

set -euo pipefail

BASE="${1:-http://localhost:8080}"
V1="${BASE}/v1"
PASS=0
FAIL=0

check() {
  local name="$1"
  local method="$2"
  local url="$3"
  local data="${4:-}"
  local expect="${5:-200}"

  if [[ "$method" == "GET" ]]; then
    code=$(curl -s -o /tmp/sentinel_resp.json -w "%{http_code}" "$url" || echo "000")
  else
    code=$(curl -s -o /tmp/sentinel_resp.json -w "%{http_code}" -X "$method" \
      -H "Content-Type: application/json" -d "$data" "$url" || echo "000")
  fi

  if [[ "$code" == "$expect" ]]; then
    echo "  ✓ $name ($code)"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $name (expected $expect, got $code)"
    cat /tmp/sentinel_resp.json 2>/dev/null | head -c 200
    echo ""
    FAIL=$((FAIL + 1))
  fi
}

echo "SentinelAI local smoke test"
echo "Base URL: $BASE"
echo ""

# Health
check "Health" GET "${BASE}/health"

# Dashboard (needs seed)
check "Dashboard" GET "${V1}/dashboard"

# Agents
check "List agents" GET "${V1}/agents"

# Register agent
check "Register agent" POST "${V1}/agents/register" \
  '{"name":"Smoke Test Agent","owner":"qa","team":"QA","purpose":"Local test","framework":"custom","risk_tier":"low","tools":[{"name":"db_query","allowed_operations":["read"]}]}'

AGENT_ID=$(python3 -c "import json; print(json.load(open('/tmp/sentinel_resp.json'))['agent']['agent_id'])" 2>/dev/null || echo "")

if [[ -n "$AGENT_ID" ]]; then
  check "Get agent" GET "${V1}/agents/${AGENT_ID}"
fi

# Policies
check "List policies" GET "${V1}/policy"

# Tool intercept — allow
if [[ -n "$AGENT_ID" ]]; then
  check "Tool intercept (allow)" POST "${V1}/tool/intercept" \
    "{\"context\":{\"agent_id\":\"${AGENT_ID}\",\"session_id\":\"smoke-1\",\"action_type\":\"read\",\"tool_name\":\"db_query\",\"tool_params\":{}},\"shadow_mode\":false}"
fi

# Decision replay (demo session from seed)
check "Decision replay" GET "${V1}/decision/replay/demo-finance-session" "200"

# Graph
check "Graph orphans" POST "${V1}/graph/query" '{"query_type":"orphans"}'

# WAF stats
check "WAF stats" GET "${V1}/waf/stats"

# Risk heatmap
check "Risk heatmap" GET "${V1}/risk/heatmap"

# Compliance
check "Compliance check" POST "${V1}/compliance/check"

# Timeline
check "Timeline" GET "${V1}/timeline"

# Violations
check "Violations" GET "${V1}/violations"

# Policy copilot
check "Policy copilot" POST "${V1}/copilot/generate-policy" \
  '{"description":"Block deleting more than 100 records after business hours","policy_name":"smoke-policy"}'

# Policy simulate
check "Policy simulate" POST "${V1}/policy/simulate" \
  '{"yaml_content":"apiVersion: sentinelai.io/v1\nkind: Policy\nmetadata:\n  name: smoke\nspec:\n  rules:\n    - name: block-delete\n      priority: 100\n      when:\n        all:\n          - context.action_type: delete\n          - context.data_scope_size >: 100\n      then:\n        action: block"}'

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
