import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query'
import type {
  DashboardResponse,
  GraphResponse,
  PoliciesResponse,
  Policy,
  PolicyDetailResponse,
  PolicySimulationResult,
  ReplayResponse,
  ViolationItem,
  WAFRecordsResponse,
  WAFStats,
  WAFEffectiveConfig,
  WAFAcceptanceReport,
  WAFTestResult,
  HitlResponse,
  TimelineResponse,
  ActionLogResponse,
  GovernanceStatus,
  AgentsResponse,
  Agent,
  HealthResponse,
  SlaCheckResponse,
  ChallengeResponse,
  GuardrailSimulationResult,
  GuardrailScenarioOutcome,
  GraphIngestResult,
  ChatSuggestionsResponse,
  ChatLlmStatus,
  ChatTurnResponse,
} from './types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ||
  'http://localhost:8080/v1'

/** Health endpoint lives at the server root, not under the /v1 prefix. */
const API_ROOT = API_BASE_URL.replace(/\/v1\/?$/, '')

/** Live polling cadence (ms) for real-time dashboards. */
export const LIVE_REFETCH_MS = 5000

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || `Request failed with status ${response.status}`)
  }

  return (await response.json()) as T
}

export function useDashboard(): UseQueryResult<DashboardResponse> {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: () => fetchJson<DashboardResponse>('/dashboard'),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export function useReplay(sessionId: string): UseQueryResult<ReplayResponse> {
  return useQuery({
    queryKey: ['replay', sessionId],
    queryFn: () => fetchJson<ReplayResponse>(`/decision/replay/${sessionId}`),
    enabled: Boolean(sessionId),
  })
}

export function useGraph(): UseQueryResult<GraphResponse> {
  return useQuery({
    queryKey: ['graph', 'full'],
    queryFn: () => fetchJson<GraphResponse>('/graph/visualize'),
  })
}

export function useOrphanAgents(): UseQueryResult<GraphResponse> {
  return useQuery({
    queryKey: ['graph', 'orphans'],
    queryFn: () =>
      fetchJson<GraphResponse>('/graph/query', {
        method: 'POST',
        body: JSON.stringify({ query_type: 'orphans' }),
      }),
  })
}

export function usePolicies(): UseQueryResult<PoliciesResponse> {
  return useQuery({
    queryKey: ['policies'],
    queryFn: () => fetchJson<PoliciesResponse>('/policy'),
  })
}

export function usePolicy(policyId: string | null): UseQueryResult<PolicyDetailResponse> {
  return useQuery({
    queryKey: ['policy', policyId],
    queryFn: () => fetchJson<PolicyDetailResponse>(`/policy/${policyId}`),
    enabled: Boolean(policyId),
  })
}

type SimulationPayload = {
  yaml_content: string
  session_id?: string | null
}

type SimulationResponse = {
  simulation: PolicySimulationResult
}

export function usePolicySimulation(): UseMutationResult<
  SimulationResponse,
  Error,
  SimulationPayload
> {
  return useMutation({
    mutationFn: (payload) =>
      fetchJson<SimulationResponse>('/policy/simulate', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  })
}

export type GeneratePolicyPayload = {
  description: string
  policy_name?: string
}

export type GeneratePolicyResponse = {
  yaml_content: string
  policy_name: string
  valid: boolean
  error?: string | null
  requires_human_approval?: boolean
  parsed_policy?: Record<string, unknown> | null
}

export function useGeneratePolicy(): UseMutationResult<
  GeneratePolicyResponse,
  Error,
  GeneratePolicyPayload
> {
  return useMutation({
    mutationFn: (payload) =>
      fetchJson<GeneratePolicyResponse>('/copilot/generate-policy', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  })
}

type DeployCopilotPayload = {
  yaml_content: string
  approved_by?: string
}

type DeployCopilotResponse = {
  policy: Policy
  message: string
}

export function useDeployCopilotPolicy(): UseMutationResult<
  DeployCopilotResponse,
  Error,
  DeployCopilotPayload
> {
  return useMutation({
    mutationFn: (payload) =>
      fetchJson<DeployCopilotResponse>('/copilot/deploy-policy', {
        method: 'POST',
        body: JSON.stringify({
          yaml_content: payload.yaml_content,
          approved_by: payload.approved_by ?? 'admin',
        }),
      }),
  })
}


type ViolationsResponse = {
  violations: ViolationItem[]
}

export function useViolations(agentId?: string): UseQueryResult<ViolationsResponse> {
  const query = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''
  return useQuery({
    queryKey: ['violations', agentId ?? 'all'],
    queryFn: () => fetchJson<ViolationsResponse>(`/violations${query}`),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export function useHitlTickets(status?: string): UseQueryResult<HitlResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return useQuery({
    queryKey: ['hitl', status ?? 'all'],
    queryFn: () => fetchJson<HitlResponse>(`/hitl${query}`),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

type HitlActionPayload = {
  ticketId: string
  action: 'approve' | 'reject'
  reviewer?: string
  reason?: string
}

export function useHitlAction(): UseMutationResult<
  { ticket_id: string; status: string; message: string },
  Error,
  HitlActionPayload
> {
  return useMutation({
    mutationFn: ({ ticketId, action, reviewer = 'admin', reason = '' }) =>
      fetchJson(`/hitl/${ticketId}/approve`, {
        method: 'POST',
        body: JSON.stringify({ action, reviewer, reason }),
      }),
  })
}

export function useGovernanceTimeline(
  agentId?: string,
  limit = 100,
): UseQueryResult<TimelineResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (agentId) {
    params.set('agent_id', agentId)
  }
  return useQuery({
    queryKey: ['timeline', agentId ?? 'all', limit],
    queryFn: () => fetchJson<TimelineResponse>(`/timeline?${params.toString()}`),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export function useGovernanceActionLog(
  agentId?: string,
  limit = 50,
): UseQueryResult<ActionLogResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (agentId) {
    params.set('agent_id', agentId)
  }
  return useQuery({
    queryKey: ['governance', 'action-log', agentId ?? 'all', limit],
    queryFn: () => fetchJson<ActionLogResponse>(`/governance/action-log?${params.toString()}`),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export function useGovernanceStatus(agentId: string | null): UseQueryResult<GovernanceStatus> {
  return useQuery({
    queryKey: ['governance', 'status', agentId],
    queryFn: () => fetchJson<GovernanceStatus>(`/governance/status/${agentId}`),
    enabled: Boolean(agentId),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export function useWAFStats(agentId?: string): UseQueryResult<WAFStats> {
  const query = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''
  return useQuery({
    queryKey: ['waf', 'stats', agentId ?? 'all'],
    queryFn: () => fetchJson<WAFStats>(`/waf/stats${query}`),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export function useWAFRecords(agentId?: string, limit = 50): UseQueryResult<WAFRecordsResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (agentId) {
    params.set('agent_id', agentId)
  }
  return useQuery({
    queryKey: ['waf', 'records', agentId ?? 'all', limit],
    queryFn: () => fetchJson<WAFRecordsResponse>(`/waf/records?${params.toString()}`),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export function useWAFConfig(agentId?: string): UseQueryResult<WAFEffectiveConfig> {
  const query = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''
  return useQuery({
    queryKey: ['waf', 'config', agentId ?? 'all'],
    queryFn: () => fetchJson<WAFEffectiveConfig>(`/waf/config${query}`),
  })
}

export function useWAFAcceptance(): UseMutationResult<WAFAcceptanceReport, Error, void> {
  return useMutation({
    mutationFn: () => fetchJson<WAFAcceptanceReport>('/waf/acceptance', { method: 'POST' }),
  })
}

export type WAFTestPayload = {
  agent_id: string
  session_id: string
  tool_name: string
  action_type: string
  tool_params?: Record<string, unknown>
  session_scope?: Record<string, unknown>
  shadow_mode?: boolean
}

export function useWAFTest(): UseMutationResult<WAFTestResult, Error, WAFTestPayload> {
  return useMutation({
    mutationFn: ({ agent_id, session_id, tool_name, action_type, tool_params, session_scope, shadow_mode }) =>
      fetchJson<WAFTestResult>('/waf/test', {
        method: 'POST',
        body: JSON.stringify({
          shadow_mode: Boolean(shadow_mode),
          context: {
            agent_id,
            session_id,
            tool_name,
            action_type,
            tool_params: tool_params ?? {},
            metadata: session_scope ? { session_scope } : {},
          },
        }),
      }),
  })
}

/* --------------------------------------------------------------
   Agents registry (PS-1.3)
   -------------------------------------------------------------- */

export function useAgents(): UseQueryResult<AgentsResponse> {
  return useQuery({
    queryKey: ['agents'],
    queryFn: () => fetchJson<AgentsResponse>('/agents'),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export function useAgent(agentId: string | null): UseQueryResult<{ agent: Agent }> {
  return useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => fetchJson<{ agent: Agent }>(`/agents/${agentId}`),
    enabled: Boolean(agentId),
  })
}

type AgentActionPayload = { agentId: string; action: 'suspend' | 'resume'; reason?: string }

export function useAgentAction(): UseMutationResult<
  { agent: Agent; message: string },
  Error,
  AgentActionPayload
> {
  return useMutation({
    mutationFn: ({ agentId, action, reason = '' }) => {
      const query = action === 'suspend' && reason ? `?reason=${encodeURIComponent(reason)}` : ''
      return fetchJson(`/agents/${agentId}/${action}${query}`, { method: 'POST' })
    },
  })
}

/* --------------------------------------------------------------
   Health
   -------------------------------------------------------------- */

export function useHealth(): UseQueryResult<HealthResponse> {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const response = await fetch(`${API_ROOT}/health`)
      if (!response.ok) throw new Error(`Health check failed (${response.status})`)
      return (await response.json()) as HealthResponse
    },
    refetchInterval: 15000,
    retry: 1,
  })
}

/* --------------------------------------------------------------
   Governance SLA sweep (PS-4.2)
   -------------------------------------------------------------- */

export function useSlaCheck(): UseMutationResult<SlaCheckResponse, Error, void> {
  return useMutation({
    mutationFn: () => fetchJson<SlaCheckResponse>('/governance/sla/check', { method: 'POST' }),
  })
}

export type IngestSignalPayload = {
  agent_id: string
  signal_type: string
  metric_value?: number
  source?: string
  reviewer?: string
}

export function useIngestSignal(): UseMutationResult<Record<string, unknown>, Error, IngestSignalPayload> {
  return useMutation({
    mutationFn: (payload) =>
      fetchJson<Record<string, unknown>>('/observability/ingest', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  })
}

/* --------------------------------------------------------------
   Decision challenge response (PS-7.1)
   -------------------------------------------------------------- */

export function useChallengeResponse(): UseMutationResult<
  ChallengeResponse,
  Error,
  { sessionId: string; question?: string }
> {
  return useMutation({
    mutationFn: ({ sessionId, question }) =>
      fetchJson<ChallengeResponse>(`/decision/challenge/${sessionId}`, {
        method: 'POST',
        body: JSON.stringify(question ? { question } : {}),
      }),
  })
}

/* --------------------------------------------------------------
   Guardrail scenario harness (PS-3.1)
   -------------------------------------------------------------- */

export function useGuardrailSimulation(): UseMutationResult<
  GuardrailSimulationResult,
  Error,
  { scenarios: GuardrailScenarioOutcome[] | Record<string, unknown>[] }
> {
  return useMutation({
    mutationFn: (payload) =>
      fetchJson<GuardrailSimulationResult>('/guardrails/simulate', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  })
}

/* --------------------------------------------------------------
   Governance graph ingestion (PS-1.3)
   -------------------------------------------------------------- */

export function useIngestRuntimeLogs(): UseMutationResult<GraphIngestResult, Error, { raw_text: string }> {
  return useMutation({
    mutationFn: (payload) =>
      fetchJson<GraphIngestResult>('/graph/ingest/runtime-logs', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  })
}

export function useIngestPolicyDocument(): UseMutationResult<
  GraphIngestResult,
  Error,
  { document: string }
> {
  return useMutation({
    mutationFn: (payload) =>
      fetchJson<GraphIngestResult>('/graph/ingest/policy-document', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  })
}

export function useReingestAgent(): UseMutationResult<GraphIngestResult, Error, string> {
  return useMutation({
    mutationFn: (agentId) =>
      fetchJson<GraphIngestResult>(`/graph/agents/${agentId}/reingest`, { method: 'POST' }),
  })
}

/* --------------------------------------------------------------
   Agent Chat — Cerebras testing (dedicated chat Lambda in prod)
   -------------------------------------------------------------- */

export function useChatSuggestions(): UseQueryResult<ChatSuggestionsResponse> {
  return useQuery({
    queryKey: ['chat', 'suggestions'],
    queryFn: () => fetchJson<ChatSuggestionsResponse>('/chat/suggestions'),
    staleTime: 60_000,
  })
}

export function useChatLlmStatus(): UseQueryResult<ChatLlmStatus> {
  return useQuery({
    queryKey: ['chat', 'llm-status'],
    queryFn: () => fetchJson<ChatLlmStatus>('/chat/llm-status'),
    staleTime: 30_000,
  })
}

export function useChatTurn(): UseMutationResult<
  ChatTurnResponse,
  Error,
  {
    message: string
    session_id: string
    history: { role: string; content: string }[]
    active_agent: string | null
  }
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) =>
      fetchJson<ChatTurnResponse>('/chat', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      void queryClient.invalidateQueries({ queryKey: ['hitl'] })
      void queryClient.invalidateQueries({ queryKey: ['violations'] })
      void queryClient.invalidateQueries({ queryKey: ['waf'] })
      void queryClient.invalidateQueries({ queryKey: ['timeline'] })
      void queryClient.invalidateQueries({ queryKey: ['governance', 'action-log'] })
    },
  })
}
