import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGovernanceActionLog,
  useGovernanceStatus,
  useGovernanceTimeline,
  useSlaCheck,
} from '../lib/api'
import { useAgent } from '../context/AgentContext'
import {
  Callout,
  EmptyState,
  ErrorState,
  Kpi,
  LoadingState,
  Panel,
  PageHeader,
  statusClass,
} from '../components/ui'
import { IconActivity, IconClock, IconShield } from '../components/icons'

export function ObservabilityPage() {
  const queryClient = useQueryClient()
  const { agentId } = useAgent()
  const [override, setOverride] = useState('')
  const effectiveAgent = (override.trim() || agentId || '') || undefined

  const timeline = useGovernanceTimeline(effectiveAgent, 120)
  const actionLog = useGovernanceActionLog(effectiveAgent, 80)
  const status = useGovernanceStatus(effectiveAgent ?? null)
  const sla = useSlaCheck()

  const mergedEvents = useMemo(() => {
    const timelineEvents =
      timeline.data?.events.map((event) => ({
        id: event.event_id ?? `${event.timestamp}-${event.event_type}`,
        timestamp: event.timestamp,
        event_type: event.event_type,
        agent_id: event.agent_id,
        payload: event.payload,
      })) ?? []
    const governanceEvents =
      actionLog.data?.actions.map((event) => ({
        id: event.event_id ?? `${event.timestamp}-${event.event_type}-gov`,
        timestamp: event.timestamp,
        event_type: event.event_type,
        agent_id: event.agent_id,
        payload: event.payload,
      })) ?? []
    const seen = new Set<string>()
    return [...timelineEvents, ...governanceEvents]
      .filter((e) => {
        if (seen.has(e.id)) return false
        seen.add(e.id)
        return true
      })
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
  }, [timeline.data, actionLog.data])

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['timeline'] })
    void queryClient.invalidateQueries({ queryKey: ['governance'] })
  }

  const statusChanges = mergedEvents.filter((e) => e.event_type === 'GovernanceStatusChanged').length
  const suspensions = mergedEvents.filter((e) => e.event_type === 'AgentSuspended').length

  if (timeline.isLoading || actionLog.isLoading) return <LoadingState label="Loading governance timeline…" />
  if (timeline.isError || actionLog.isError) {
    return <ErrorState>Failed to load governance timeline. Verify the backend is running on <code>localhost:8080</code>.</ErrorState>
  }

  return (
    <section className="page-section">
      <PageHeader
        eyebrow={<><IconActivity width={13} height={13} /> PS-4.2 · Observability → Governance</>}
        title="Observability & SLA"
        subtitle="Runtime signals drive the governance state machine — agents move GREEN → UNDER_REVIEW → REMEDIATED, and time-bound review SLAs auto-escalate. This is the live, unified governance event stream."
        actions={
          <label className="filter-field">
            <span className="muted small">Filter by agent ID {agentId ? '(global focus active)' : ''}</span>
            <input
              value={override}
              onChange={(e) => setOverride(e.target.value)}
              placeholder={agentId ?? 'agent-…'}
            />
          </label>
        }
      />

      <div className="kpi-grid">
        <Kpi label="Events" value={mergedEvents.length} icon={<IconActivity width={16} height={16} />} />
        <Kpi label="Status changes" value={statusChanges} />
        <Kpi label="Suspensions" value={suspensions} />
        <Kpi
          label="Focused status"
          value={<span className="metric-text">{effectiveAgent ? (status.data?.status ?? '—') : 'all'}</span>}
          icon={<IconShield width={16} height={16} />}
        />
      </div>

      <Panel title="Governance SLA" icon={<IconClock width={18} height={18} />} action={
        <button type="button" className="btn primary" disabled={sla.isPending} onClick={() => sla.mutate(undefined, { onSuccess: invalidate })}>
          {sla.isPending ? 'Running sweep…' : 'Run SLA sweep'}
        </button>
      }>
        <Callout variant="warn">
          The SLA sweep runs on a 15-minute EventBridge schedule in production. Agents held in review past their SLA are
          escalated automatically; reminders fire at the halfway mark. Run it on demand here.
        </Callout>
        {sla.isError ? <p className="error-text small">{sla.error.message}</p> : null}
        {sla.data ? (
          <div className="stack-list compact" style={{ marginTop: 12 }}>
            <div className="list-row"><span className="muted">SLA window</span><strong>{Number(sla.data.sla_hours ?? 0)}h</strong></div>
            <div className="list-row"><span className="muted">Reminders sent</span><strong>{(sla.data.reminders as unknown[])?.length ?? 0}</strong></div>
            <div className="list-row"><span className="muted">Escalations</span><strong>{(sla.data.escalations as unknown[])?.length ?? 0}</strong></div>
            <div className="list-row"><span className="muted">Checked at</span><strong className="small">{sla.data.checked_at ? new Date(String(sla.data.checked_at)).toLocaleTimeString() : '—'}</strong></div>
          </div>
        ) : null}
      </Panel>

      <Panel title="Unified governance event stream" icon={<IconActivity width={18} height={18} />} action={<span className="muted small">{mergedEvents.length} events</span>}>
        {mergedEvents.length === 0 ? (
          <EmptyState title="No governance events yet" hint="Governance transitions and runtime signals will stream here as agents act." />
        ) : (
          <div className="timeline-list">
            {mergedEvents.map((event) => (
              <div key={event.id} className="timeline-item">
                <div className="timeline-marker" />
                <div className="timeline-content">
                  <div className="timeline-meta">
                    <strong>{event.event_type}</strong>
                    <span className="muted small">{new Date(event.timestamp).toLocaleString()}</span>
                  </div>
                  <p className="mono small" style={{ margin: '2px 0' }}>{event.agent_id}</p>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    {'governance_status' in event.payload ? (
                      <span className={`badge ${statusClass(String(event.payload.governance_status))}`}>{String(event.payload.governance_status)}</span>
                    ) : null}
                    {'from_status' in event.payload && 'to_status' in event.payload ? (
                      <span className="muted small">{String(event.payload.from_status)} → {String(event.payload.to_status)}</span>
                    ) : null}
                    {'signal_type' in event.payload ? (
                      <span className="muted small">signal: {String(event.payload.signal_type)}</span>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </section>
  )
}
