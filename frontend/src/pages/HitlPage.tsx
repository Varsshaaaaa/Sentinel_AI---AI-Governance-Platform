import { useQueryClient } from '@tanstack/react-query'
import { useHitlAction, useHitlTickets } from '../lib/api'
import { EmptyState, ErrorState, Kpi, LoadingState, Panel, PageHeader, riskClass } from '../components/ui'
import { IconUsersCheck } from '../components/icons'

export function HitlPage() {
  const queryClient = useQueryClient()
  const tickets = useHitlTickets('pending')
  const hitlAction = useHitlAction()

  if (tickets.isLoading) return <LoadingState label="Loading HITL queue…" />
  if (tickets.isError || !tickets.data) {
    return <ErrorState>Failed to load HITL tickets. Verify the backend is running on <code>localhost:8080</code>.</ErrorState>
  }

  const pending = tickets.data.tickets

  async function handleAction(ticketId: string, action: 'approve' | 'reject') {
    await hitlAction.mutateAsync({ ticketId, action })
    await queryClient.invalidateQueries({ queryKey: ['hitl'] })
  }

  return (
    <section className="page-section">
      <PageHeader
        eyebrow={<><IconUsersCheck width={13} height={13} /> PS-3.1 · Human Oversight</>}
        title="Human-in-the-loop Queue"
        subtitle="High-risk agent actions that guardrails escalated for human approval. Approve to release the action, or reject to keep it blocked — every decision is audit-logged."
        actions={<span className="status-pill">{pending.length} pending</span>}
      />

      <div className="kpi-grid">
        <Kpi label="Pending approvals" value={pending.length} icon={<IconUsersCheck width={16} height={16} />} />
        <Kpi label="High-risk (≥75)" value={pending.filter((t) => Number(t.risk_score ?? 0) >= 75).length} />
      </div>

      {pending.length === 0 ? (
        <Panel>
          <EmptyState title="Queue is clear" hint="No pending HITL tickets. High-risk actions will surface here for review." />
        </Panel>
      ) : (
        <div className="card-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))' }}>
          {pending.map((ticket) => (
            <article key={ticket.ticket_id} className="panel">
              <div className="panel-header">
                <h3 className="with-icon"><IconUsersCheck width={16} height={16} />{ticket.tool_name}</h3>
                {ticket.risk_score != null ? (
                  <span className={`badge ${riskClass(Number(ticket.risk_score))}`}>risk {ticket.risk_score}</span>
                ) : <span className="badge status-amber">{ticket.status}</span>}
              </div>
              <dl className="detail-list">
                <div><dt>Agent</dt><dd className="mono small">{ticket.agent_id}</dd></div>
                <div><dt>Session</dt><dd className="mono small">{ticket.session_id}</dd></div>
                <div><dt>Reason</dt><dd style={{ textAlign: 'right' }}>{ticket.reason}</dd></div>
              </dl>
              <div className="button-row">
                <button type="button" className="btn primary" disabled={hitlAction.isPending} onClick={() => void handleAction(ticket.ticket_id, 'approve')}>Approve</button>
                <button type="button" className="btn danger" disabled={hitlAction.isPending} onClick={() => void handleAction(ticket.ticket_id, 'reject')}>Reject</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
