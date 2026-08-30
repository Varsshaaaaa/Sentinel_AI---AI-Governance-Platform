import { useState } from 'react'
import { useReplay } from '../lib/api'
import { useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState, Kpi, Panel, PageHeader } from '../components/ui'
import { IconReplay, IconScroll } from '../components/icons'

const defaultSessionId = 'demo-finance-session'

export function ReplayPage() {
  const [searchParams] = useSearchParams()
  const initialSession = searchParams.get('session')?.trim() || defaultSessionId
  const [sessionInput, setSessionInput] = useState(initialSession)
  const [sessionId, setSessionId] = useState(initialSession)
  const replay = useReplay(sessionId)

  return (
    <section className="page-section">
      <PageHeader
        eyebrow={<><IconReplay width={13} height={13} /> PS-7.1 · Decision Provenance</>}
        title="Decision Replay"
        subtitle="Reconstruct the full causal timeline of any governed session — inputs, tool calls, policy evaluation, and risk scoring — as an immutable, PII-redacted audit trail queryable by session ID."
      />

      <Panel title="Load a session" icon={<IconReplay width={18} height={18} />}>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault()
            setSessionId(sessionInput.trim())
          }}
        >
          <label className="field">
            <span>Session ID</span>
            <input value={sessionInput} onChange={(e) => setSessionInput(e.target.value)} placeholder="demo-finance-session" />
          </label>
          <button type="submit" className="btn primary">Load replay</button>
        </form>
      </Panel>

      {replay.isLoading ? <div className="page-state">Loading replay…</div> : null}
      {replay.isError ? <ErrorState>Could not load replay for <code>{sessionId}</code>.</ErrorState> : null}

      {replay.data ? (
        <>
          <div className="kpi-grid">
            <Kpi label="Agent" value={<span className="metric-text">{replay.data.agent_id}</span>} />
            <Kpi label="User" value={<span className="metric-text">{replay.data.user_id}</span>} />
            <Kpi label="Steps" value={replay.data.step_count} icon={<IconReplay width={16} height={16} />} />
          </div>

          <Panel title="Session summary" icon={<IconScroll width={18} height={18} />}>
            <p>{replay.data.summary}</p>
            <div className="subpanel">
              <h4 style={{ marginBottom: 6 }}>LLM summary</h4>
              <p className="muted">{replay.data.llm_summary || 'No LLM summary available in the current environment.'}</p>
            </div>
          </Panel>

          <Panel title="Decision timeline" icon={<IconReplay width={18} height={18} />} action={<span className="muted small">{replay.data.timeline.length} steps</span>}>
            {replay.data.timeline.length === 0 ? (
              <EmptyState title="No steps recorded" hint="This session has no audit steps yet." />
            ) : (
              <div className="timeline-list">
                {replay.data.timeline.map((step) => (
                  <div key={step.sequence} className="timeline-item large">
                    <div className="timeline-marker" />
                    <div className="timeline-content">
                      <div className="timeline-meta">
                        <strong>Step {step.sequence} · {step.step_type}</strong>
                        <span className="muted small">{new Date(step.timestamp).toLocaleString()}</span>
                      </div>
                      {typeof step.risk_score === 'number' ? (
                        <p className="muted small" style={{ margin: '4px 0' }}>Risk score: {step.risk_score}</p>
                      ) : null}
                      <pre className="json-preview">{JSON.stringify(step.content, null, 2)}</pre>
                      {step.policy_evaluation ? (
                        <details>
                          <summary className="muted small">Policy evaluation</summary>
                          <pre className="json-preview">{JSON.stringify(step.policy_evaluation, null, 2)}</pre>
                        </details>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </>
      ) : null}
    </section>
  )
}
