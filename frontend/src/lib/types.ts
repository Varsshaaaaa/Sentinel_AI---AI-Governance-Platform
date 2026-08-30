export type Summary = {
  total_agents: number
  active_agents: number
  suspended_agents: number
  total_violations: number
  violations_24h: number
  avg_risk_score: number
  compliance_green: number
  compliance_amber: number
  compliance_red: number
}

export type DashboardRiskItem = {
  agent_id: string
  agent_name?: string
  risk_score: number
  risk_level?: string
}

export type ComplianceItem = {
  agent_id: string
  compliance_status: string
  guardrails_active?: boolean
  hitl_configured?: boolean
  audit_logging_enabled?: boolean
}

export type EventItem = {
  event_id?: string
  event_type: string
  agent_id: string
  actor?: string
  timestamp: string
  payload: Record<string, unknown>
}

export type ViolationItem = {
  violation_id: string
  agent_id: string
  session_id?: string
  rule_name: string
  severity: string
  source?: string
  reason: string
  timestamp: string
}

export type DashboardResponse = {
  summary: Summary
  risk_heatmap: DashboardRiskItem[]
  compliance: ComplianceItem[]
  recent_events: EventItem[]
  recent_violations: ViolationItem[]
}

export type ReplayTimelineStep = {
  sequence: number
  timestamp: string
  step_type: string
  content: Record<string, unknown>
  policy_evaluation?: Record<string, unknown> | null
  risk_score?: number | null
}

export type ReplayResponse = {
  session_id: string
  agent_id: string
  user_id: string
  started_at: string | null
  completed_at: string | null
  timeline: ReplayTimelineStep[]
  summary: string
  llm_summary?: string | null
  step_count: number
}

export type GraphNode = {
  node_id: string
  node_type: string
  label: string
  properties: Record<string, unknown>
}

export type GraphEdge = {
  source_id: string
  target_id: string
  edge_type: string
  properties: Record<string, unknown>
}

export type GraphResponse = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  metadata?: Record<string, unknown>
}

export type PolicyRule = {
  name: string
  priority: number
  when: unknown
  then: Record<string, unknown>
}

export type Policy = {
  policy_id: string
  name: string
  description: string
  inherits?: string | null
  rules: PolicyRule[]
  status: string
  created_at: string
  updated_at: string
}

export type PoliciesResponse = {
  policies: Policy[]
}

export type PolicyDetailResponse = {
  policy: Policy
}

export type PolicySimulationResult = {
  changed_decisions?: unknown[]
  simulated_step_count?: number
  old_policy_count?: number
  [key: string]: unknown
}

export type WAFRuleEvaluation = {
  rule_type: string
  rule_id: string
  passed: boolean
  detail: string
}

export type WAFRecord = {
  record_id: string
  agent_id: string
  session_id: string
  tool_name: string
  action_type?: string
  disposition: string
  matched_rules: string[]
  evaluations?: WAFRuleEvaluation[]
  reason: string
  params_sanitized?: Record<string, unknown>
  shadow_mode: boolean
  latency_ms: number
  timestamp: string
}

export type WAFStats = {
  agent_id: string | null
  total_calls: number
  allowed: number
  denied: number
  shadow_would_deny: number
  by_tool: Record<string, number>
  by_rule_type: Record<string, number>
  avg_latency_ms: number
  recent_blocks: WAFRecord[]
}

export type WAFRecordsResponse = {
  records: WAFRecord[]
}

export type WAFEffectiveConfig = {
  agent_id: string | null
  enabled: boolean
  rate_window_seconds: number
  rate_limits: Record<string, number>
  max_param_size: number
  injection_patterns: string[]
  param_blocklist: string[]
  allowed_datasets: string[]
  sequence_rules: Record<string, string[]>
  allowed_tools: string[]
  source: string
}

export type WAFAcceptanceCriterion = {
  id: string
  ps_criterion: string
  scenario: string
  expected: string
  actual: string
  passed: boolean
  evidence: {
    disposition?: string
    matched_rules?: string[]
    reason?: string
    trace?: WAFRuleEvaluation[]
    [key: string]: unknown
  }
}

export type WAFAcceptanceReport = {
  suite: string
  passed: boolean
  summary: { total: number; passed: number; failed: number }
  criteria: WAFAcceptanceCriterion[]
}

export type WAFTestResult = {
  disposition: string
  matched_rules: string[]
  evaluations: WAFRuleEvaluation[]
  reason: string
}

export type HitlTicket = {
  ticket_id: string
  agent_id: string
  session_id: string
  user_id?: string
  tool_name: string
  tool_params?: Record<string, unknown>
  action_type?: string
  reason: string
  status: string
  reviewer?: string | null
  risk_score?: number
}

export type HitlResponse = {
  tickets: HitlTicket[]
}

export type GovernanceStatus = {
  agent_id: string
  status: string
  since: string
  trigger_signal?: string | null
  reviewer?: string | null
}

export type TimelineResponse = {
  events: EventItem[]
}

export type ActionLogResponse = {
  actions: EventItem[]
}

export type AgentModel = { name: string; provider?: string; version?: string }
export type AgentTool = { name: string; allowed_operations?: string[]; data_scope?: Record<string, unknown> }

export type Agent = {
  agent_id: string
  name?: string
  owner?: string
  team?: string
  purpose?: string
  framework?: string
  status?: string
  risk_tier?: string
  models?: AgentModel[]
  tools?: AgentTool[]
  datasets?: string[]
  policy_ids?: string[]
  created_at?: string
  last_active_at?: string | null
  /** Injected client-side from the dashboard risk heatmap. */
  risk_score?: number
  [key: string]: unknown
}

export type AgentsResponse = {
  agents: Agent[]
  count: number
}

export type HealthResponse = {
  status: string
  [key: string]: unknown
}

export type SlaCheckResponse = {
  checked_at?: string
  sla_hours?: number
  reminders?: unknown[]
  escalations?: unknown[]
  [key: string]: unknown
}

export type ChallengeResponse = {
  session_id?: string
  agent_id?: string
  challenge_question?: string
  draft_response?: string
  final_action?: string
  tools_used?: string[]
  data_considered?: string[]
  rules_applied?: string[]
  [key: string]: unknown
}

export type GuardrailScenarioOutcome = {
  name?: string
  disposition?: string
  action?: string
  matched_rules?: string[]
  risk_score?: number
  expected?: string | null
  matched_expectation?: boolean
  reason?: string
  [key: string]: unknown
}

export type GuardrailSimulationResult = {
  total?: number
  outcomes_covered?: string[]
  covers_all_three_outcomes?: boolean
  expectations_met?: boolean
  results?: GuardrailScenarioOutcome[]
  [key: string]: unknown
}

export type GraphIngestResult = {
  nodes_added?: number
  edges_added?: number
  diff?: Record<string, unknown>
  [key: string]: unknown
}

export type ChatSuggestionItem = {
  text: string
  expected?: string
  reason?: string
}

export type ChatSuggestionsResponse = {
  try_asking: string[]
  deny_block: ChatSuggestionItem[]
  hitl: ChatSuggestionItem[]
}

export type ChatLlmStatus = {
  configured: boolean
  model: string | null
}

export type ChatEvent = {
  kind: string
  content?: string
  agent_name?: string
  reason?: string
  tool_name?: string
  params?: Record<string, unknown>
  disposition?: string
  request?: Record<string, unknown>
  response?: Record<string, unknown>
  [key: string]: unknown
}

export type ChatTurnResponse = {
  ok: boolean
  error?: string
  reply?: string
  session_id?: string
  agent_id?: string
  agent_name?: string
  events?: ChatEvent[]
  history?: { role: string; content: string }[]
}
