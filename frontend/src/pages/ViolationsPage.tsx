import { useViolations } from '../lib/api'
import { useAgent } from '../context/AgentContext'
import { EmptyState, ErrorState, Kpi, LoadingState, Panel, PageHeader } from '../components/ui'
import { IconAlert } from '../components/icons'

function severityClass(severity: string): string {
  const s = severity.toLowerCase()
  if (s === 'critical' || s === 'high') return 'status-red'
  if (s === 'medium') return 'status-amber'
  return 'severity-low'
}

export function ViolationsPage() {
  const { agentId } = useAgent()
  const violations = useViolations(agentId ?? undefined)

  if (violations.isLoading) return <LoadingState label="Loading violations…" />
  if (violations.isError || !violations.data) {
    return <ErrorState>Failed to load violations. Verify the backend is running on <code>localhost:8080</code>.</ErrorState>
  }

  const items = violations.data.violations
  const high = items.filter((v) => ['high', 'critical'].includes(v.severity.toLowerCase())).length
  const medium = items.filter((v) => v.severity.toLowerCase() === 'medium').length

  return (
    <section className="page-section">
      <PageHeader
        eyebrow={<><IconAlert width={13} height={13} /> PS-3.1 · Enforcement Ledger</>}
        title="Policy Violations"
        subtitle="Every guardrail and WAF violation recorded across governed sessions. Deny events, blocked bulk actions, and out-of-scope reads all land here as an immutable ledger."
        actions={<span className="status-pill">{items.length} total{agentId ? ` · ${agentId}` : ''}</span>}
      />

      <div className="kpi-grid">
        <Kpi label="Total violations" value={items.length} icon={<IconAlert width={16} height={16} />} />
        <Kpi label="High / critical" value={high} />
        <Kpi label="Medium" value={medium} />
      </div>

      <Panel title="Violation ledger" icon={<IconAlert width={18} height={18} />}>
        {items.length === 0 ? (
          <EmptyState title="No violations recorded" hint="Guardrail and WAF denials will appear here as agents run." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Agent</th>
                  <th>Session</th>
                  <th>Rule</th>
                  <th>Severity</th>
                  <th>Source</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.violation_id}>
                    <td className="mono small">{new Date(item.timestamp).toLocaleString()}</td>
                    <td className="mono small">{item.agent_id}</td>
                    <td className="mono small">{item.session_id ?? '—'}</td>
                    <td>{item.rule_name}</td>
                    <td><span className={`badge ${severityClass(item.severity)}`}>{item.severity}</span></td>
                    <td className="small muted">{item.source ?? 'guardrails'}</td>
                    <td className="small">{item.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </section>
  )
}
