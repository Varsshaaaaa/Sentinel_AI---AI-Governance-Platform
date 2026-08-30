import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAgentAction, useAgents, useDashboard } from '../lib/api'
import { useAgent as useAgentContext } from '../context/AgentContext'
import {
  Callout,
  EmptyState,
  ErrorState,
  Kpi,
  LoadingState,
  Panel,
  PageHeader,
  riskClass,
  statusClass,
} from '../components/ui'
import { IconExternal, IconRobot, IconSearch } from '../components/icons'
import type { Agent } from '../lib/types'

function agentStatus(agent: Agent): string {
  return String(agent.status ?? 'active')
}

function toolNames(agent: Agent): string[] {
  return (agent.tools ?? []).map((t) => (typeof t === 'string' ? t : t?.name)).filter(Boolean) as string[]
}

function modelNames(agent: Agent): string[] {
  return (agent.models ?? []).map((m) => (typeof m === 'string' ? m : m?.name)).filter(Boolean) as string[]
}

export function AgentsPage() {
  const queryClient = useQueryClient()
  const agents = useAgents()
  const dashboard = useDashboard()
  const action = useAgentAction()
  const { agentId, setAgentId } = useAgentContext()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)

  // Numeric risk scores live in the dashboard heatmap; merge them onto agents.
  const riskById = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of dashboard.data?.risk_heatmap ?? []) map.set(r.agent_id, Number(r.risk_score ?? 0))
    return map
  }, [dashboard.data])

  const list = useMemo<Agent[]>(
    () => (agents.data?.agents ?? []).map((a) => ({ ...a, risk_score: riskById.get(a.agent_id) ?? a.risk_score })),
    [agents.data, riskById],
  )
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return list
    return list.filter(
      (a) =>
        a.agent_id.toLowerCase().includes(q) ||
        String(a.name ?? '').toLowerCase().includes(q) ||
        String(a.owner ?? '').toLowerCase().includes(q),
    )
  }, [list, search])

  const activeSelection = selected ?? agentId
  const detail = list.find((a) => a.agent_id === activeSelection) ?? null

  const stats = useMemo(() => {
    const active = list.filter((a) => agentStatus(a) === 'active').length
    const suspended = list.filter((a) => agentStatus(a) === 'suspended').length
    const scored = list.filter((a) => typeof a.risk_score === 'number')
    const avgRisk =
      scored.length > 0
        ? Math.round((scored.reduce((sum, a) => sum + Number(a.risk_score ?? 0), 0) / scored.length) * 10) / 10
        : 0
    return { active, suspended, avgRisk }
  }, [list])

  async function runAction(id: string, act: 'suspend' | 'resume') {
    await action.mutateAsync({ agentId: id, action: act, reason: act === 'suspend' ? 'Manual suspension from console' : '' })
    await queryClient.invalidateQueries({ queryKey: ['agents'] })
    await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  }

  if (agents.isLoading) return <LoadingState label="Loading agent registry…" />
  if (agents.isError) {
    return <ErrorState>Failed to load agents. Verify the backend is running on <code>localhost:8080</code>.</ErrorState>
  }

  return (
    <section className="page-section">
      <PageHeader
        eyebrow={<><IconRobot width={13} height={13} /> PS-1.3 · Inventory</>}
        title="Agent Registry"
        subtitle="Every governed autonomous agent, its composition, live risk posture, and governance state. Suspend a rogue agent instantly or scope the whole console to one agent."
        actions={
          <label className="agent-select" style={{ minWidth: 240 }}>
            <IconSearch width={16} height={16} />
            <input
              style={{ border: 'none', background: 'transparent', outline: 'none', color: 'inherit', width: '100%' }}
              placeholder="Search by id, name, owner…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        }
      />

      <div className="kpi-grid">
        <Kpi label="Total agents" value={list.length} icon={<IconRobot width={16} height={16} />} />
        <Kpi label="Active" value={stats.active} hint="Currently permitted to act" />
        <Kpi label="Suspended" value={stats.suspended} hint="Blocked from all tool calls" />
        <Kpi label="Average risk" value={stats.avgRisk} />
      </div>

      <div className="two-column">
        <Panel title="Registry" icon={<IconRobot width={18} height={18} />} action={<span className="muted small">{filtered.length} shown</span>}>
          {filtered.length === 0 ? (
            <EmptyState title="No agents found" hint="Register agents via POST /v1/agents/register or adjust your search." />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Status</th>
                    <th>Risk</th>
                    <th>Model</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((agent) => {
                    const status = agentStatus(agent)
                    const hasRisk = typeof agent.risk_score === 'number'
                    const risk = Number(agent.risk_score ?? 0)
                    return (
                      <tr
                        key={agent.agent_id}
                        style={{ cursor: 'pointer', background: activeSelection === agent.agent_id ? 'rgba(56,189,248,0.06)' : undefined }}
                        onClick={() => setSelected(agent.agent_id)}
                      >
                        <td>
                          <strong>{agent.name || agent.agent_id}</strong>
                          <div className="muted small mono">{agent.agent_id}</div>
                        </td>
                        <td><span className={`badge ${statusClass(status)}`}>{status}</span></td>
                        <td>
                          {hasRisk ? (
                            <span className={`badge ${riskClass(risk)}`}>{risk}</span>
                          ) : (
                            <span className={`badge ${statusClass(String(agent.risk_tier ?? ''))}`}>{agent.risk_tier ?? '—'}</span>
                          )}
                        </td>
                        <td className="small muted">{modelNames(agent).join(', ') || '—'}</td>
                        <td>
                          {status === 'suspended' ? (
                            <button
                              type="button"
                              className="btn sm"
                              disabled={action.isPending}
                              onClick={(e) => { e.stopPropagation(); void runAction(agent.agent_id, 'resume') }}
                            >
                              Resume
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="btn sm danger"
                              disabled={action.isPending}
                              onClick={(e) => { e.stopPropagation(); void runAction(agent.agent_id, 'suspend') }}
                            >
                              Suspend
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Agent detail" icon={<IconExternal width={18} height={18} />}>
          {!detail ? (
            <EmptyState title="Select an agent" hint="Choose an agent from the registry to inspect its composition and controls." />
          ) : (
            <div className="field-group">
              <div>
                <h3 style={{ marginBottom: 4 }}>{detail.name || detail.agent_id}</h3>
                <p className="muted small mono" style={{ margin: 0 }}>{detail.agent_id}</p>
              </div>
              <dl className="detail-list">
                <div><dt>Status</dt><dd><span className={`badge ${statusClass(agentStatus(detail))}`}>{agentStatus(detail)}</span></dd></div>
                <div><dt>Owner</dt><dd>{detail.owner || '—'}{detail.team ? ` · ${detail.team}` : ''}</dd></div>
                <div>
                  <dt>Risk</dt>
                  <dd>
                    {typeof detail.risk_score === 'number' ? (
                      <span className={`badge ${riskClass(detail.risk_score)}`}>{detail.risk_score}</span>
                    ) : (
                      <span className={`badge ${statusClass(String(detail.risk_tier ?? ''))}`}>{detail.risk_tier ?? '—'}</span>
                    )}
                  </dd>
                </div>
                <div><dt>Framework</dt><dd>{detail.framework || '—'}</dd></div>
                <div><dt>Models</dt><dd>{modelNames(detail).join(', ') || '—'}</dd></div>
                <div><dt>Datasets</dt><dd>{(detail.datasets ?? []).length || '—'}</dd></div>
                <div><dt>Policies</dt><dd>{(detail.policy_ids ?? []).length || '—'}</dd></div>
              </dl>

              {detail.purpose ? <p className="muted small" style={{ margin: 0 }}>{detail.purpose}</p> : null}

              {toolNames(detail).length > 0 ? (
                <div>
                  <p className="muted small" style={{ marginBottom: 6 }}>Tools</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {toolNames(detail).map((t) => (
                      <span key={t} className="tech-tag" style={{ textTransform: 'none' }}>{t}</span>
                    ))}
                  </div>
                </div>
              ) : null}

              {(detail.datasets ?? []).length > 0 ? (
                <div>
                  <p className="muted small" style={{ marginBottom: 6 }}>Datasets</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {(detail.datasets ?? []).map((d) => (
                      <span key={String(d)} className="tech-tag" style={{ textTransform: 'none' }}>{String(d)}</span>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="button-row">
                <button
                  type="button"
                  className={agentId === detail.agent_id ? 'btn primary' : 'btn'}
                  onClick={() => setAgentId(agentId === detail.agent_id ? null : detail.agent_id)}
                >
                  {agentId === detail.agent_id ? 'Focused (clear)' : 'Focus console on agent'}
                </button>
              </div>

              {action.isError ? <p className="error-text small">{action.error.message}</p> : null}
            </div>
          )}
        </Panel>
      </div>

      <Callout>
        Suspending an agent immediately blocks all its tool calls at the WAF layer and flips its governance
        posture to red. Use <strong>Focus console on agent</strong> to filter every page to a single agent.
      </Callout>
    </section>
  )
}
