import { Fragment, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useWAFAcceptance, useWAFConfig, useWAFRecords, useWAFStats } from '../lib/api'
import { useAgent } from '../context/AgentContext'
import { Callout, EmptyState, ErrorState, Kpi, LoadingState, Panel, PageHeader, Tabs } from '../components/ui'
import { IconFirewall, IconBolt, IconShield } from '../components/icons'
import type { WAFRecord, WAFRuleEvaluation } from '../lib/types'

const WAF_WEBSOCKET_URL = (import.meta.env.VITE_WAF_WEBSOCKET_URL as string | undefined)?.trim()

function dispositionClass(disposition: string): string {
  if (disposition === 'allow') return 'status-green'
  if (disposition === 'shadow') return 'status-amber'
  return 'status-red'
}

const RULE_TYPE_LABELS: Record<string, string> = {
  tool_scope: 'Tool scope',
  rate_limit: 'Rate limit',
  parameter_validation: 'Parameter validation',
  size_limit: 'Payload size',
  data_scope: 'Data scope',
  sequence: 'Sequence order',
}

type TabId = 'overview' | 'acceptance' | 'ruleset'

export function WafPage() {
  const { agentId } = useAgent()
  const [tab, setTab] = useState<TabId>('overview')

  return (
    <section className="page-section">
      <PageHeader
        eyebrow={<><IconFirewall width={13} height={13} /> PS-5.1 · Runtime Firewall for Tool Calls</>}
        title="Agent WAF"
        subtitle="A firewall that inspects, filters, and logs every tool invocation before it executes — enforcing rate limits, parameter validation, data-scope, and sequence rules, with shadow mode and a full per-rule evaluation trace on every decision."
      />

      <Tabs<TabId>
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'overview', label: 'Live Overview' },
          { id: 'acceptance', label: 'Acceptance Suite' },
          { id: 'ruleset', label: 'Effective Ruleset' },
        ]}
      />

      {tab === 'overview' ? <OverviewTab agentId={agentId ?? undefined} /> : null}
      {tab === 'acceptance' ? <AcceptanceTab /> : null}
      {tab === 'ruleset' ? <RulesetTab agentId={agentId ?? undefined} /> : null}
    </section>
  )
}

/* ----------------------------- Overview ----------------------------- */

function OverviewTab({ agentId }: { agentId?: string }) {
  const queryClient = useQueryClient()
  // Fleet-wide stats on overview; per-agent filter only on the live log.
  const stats = useWAFStats()
  const records = useWAFRecords(agentId, 60)
  const [liveRecords, setLiveRecords] = useState<WAFRecord[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)
  const [wsStatus, setWsStatus] = useState<'idle' | 'connecting' | 'connected' | 'error' | 'unconfigured'>(
    WAF_WEBSOCKET_URL ? 'idle' : 'unconfigured',
  )

  useEffect(() => {
    if (records.data?.records) setLiveRecords(records.data.records)
  }, [records.data])

  useEffect(() => {
    if (!WAF_WEBSOCKET_URL) return
    setWsStatus('connecting')
    const socket = new WebSocket(WAF_WEBSOCKET_URL)
    socket.onopen = () => setWsStatus('connected')
    socket.onerror = () => setWsStatus('error')
    socket.onclose = () => setWsStatus('error')
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as WAFRecord | { type: string }
      if ('type' in payload && payload.type === 'heartbeat') return
      setLiveRecords((current) =>
        [payload as WAFRecord, ...current.filter((r) => r.record_id !== (payload as WAFRecord).record_id)].slice(0, 60),
      )
      void queryClient.invalidateQueries({ queryKey: ['waf', 'stats'] })
    }
    const ping = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action: 'ping' }))
    }, 30000)
    return () => {
      window.clearInterval(ping)
      socket.close()
    }
  }, [queryClient])

  const toolChartData = useMemo(
    () => Object.entries(stats.data?.by_tool ?? {}).map(([tool, count]) => ({ tool, count })),
    [stats.data],
  )
  const ruleChartData = useMemo(
    () =>
      Object.entries(stats.data?.by_rule_type ?? {}).map(([rule, count]) => ({
        rule: RULE_TYPE_LABELS[rule] ?? rule,
        count,
      })),
    [stats.data],
  )

  if (stats.isLoading) return <LoadingState label="Loading WAF dashboard…" />
  if (stats.isError || !stats.data) {
    return <ErrorState>Failed to load WAF stats. Start the backend on <code>localhost:8080</code>.</ErrorState>
  }

  const denyRatio = stats.data.total_calls > 0 ? Math.round((stats.data.denied / stats.data.total_calls) * 100) : 0
  const wsLabel =
    wsStatus === 'connected'
      ? 'Live WebSocket connected'
      : wsStatus === 'unconfigured'
        ? 'Polling every 5s (set VITE_WAF_WEBSOCKET_URL for push)'
        : `WebSocket: ${wsStatus}`

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
        <span className="status-pill">
          <span className={`health-dot ${wsStatus === 'connected' ? 'ok' : ''}`} />
          {wsLabel}
        </span>
      </div>

      <div className="kpi-grid">
        <Kpi label="Total calls" value={stats.data.total_calls} icon={<IconFirewall width={16} height={16} />} />
        <Kpi label="Allowed" value={stats.data.allowed} />
        <Kpi
          label="Denied"
          value={stats.data.denied}
          delta={{ dir: denyRatio > 20 ? 'up' : 'down', text: `${denyRatio}% deny ratio` }}
        />
        <Kpi label="Avg latency" value={`${stats.data.avg_latency_ms ?? 0} ms`} hint="Per interception" />
      </div>

      <div className="two-column">
        <Panel title="Traffic by tool" icon={<IconFirewall width={18} height={18} />}>
          <div className="chart-wrap">
            {toolChartData.length ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={toolChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="tool" tick={{ fill: '#64748b', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip
                    cursor={{ fill: 'rgba(37, 99, 235, 0.06)' }}
                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, color: '#0f172a' }}
                  />
                  <Bar dataKey="count" radius={[8, 8, 0, 0]} fill="#2563eb" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState title="No WAF traffic yet" hint="Fire calls from the Attack Lab or send through /v1/tool/intercept." />
            )}
          </div>
        </Panel>

        <Panel title="Blocks by rule type" icon={<IconShield width={18} height={18} />}>
          <div className="chart-wrap">
            {ruleChartData.length ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={ruleChartData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="rule" width={130} tick={{ fill: '#64748b', fontSize: 11 }} />
                  <Tooltip
                    cursor={{ fill: 'rgba(239, 68, 68, 0.06)' }}
                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, color: '#0f172a' }}
                  />
                  <Bar dataKey="count" radius={[0, 8, 8, 0]} fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState title="No blocks yet" hint="Blocked calls are attributed to the rule that tripped them." />
            )}
          </div>
        </Panel>
      </div>

      <Panel
        title="Live intercept log"
        icon={<IconBolt width={18} height={18} />}
        action={<span className="muted small">{liveRecords.length} events · click a row for the rule trace</span>}
      >
        {liveRecords.length === 0 ? (
          <EmptyState title="No intercepts yet" hint="Tool calls will stream here as agents act." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Tool</th>
                  <th>Action</th>
                  <th>Disposition</th>
                  <th>Tripped rule</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {liveRecords.map((record) => {
                  const isOpen = expanded === record.record_id
                  return (
                    <Fragment key={record.record_id}>
                      <tr
                        onClick={() => setExpanded(isOpen ? null : record.record_id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td className="small">{new Date(record.timestamp).toLocaleTimeString()}</td>
                        <td>{record.tool_name}</td>
                        <td className="small muted">{record.action_type || '—'}</td>
                        <td>
                          <span className={`badge ${dispositionClass(record.disposition)}`}>{record.disposition}</span>
                        </td>
                        <td className="small muted">{record.matched_rules.join(', ') || 'all passed'}</td>
                        <td className="small">{record.latency_ms} ms</td>
                      </tr>
                      {isOpen ? (
                        <tr>
                          <td colSpan={6} style={{ background: 'var(--surface-2)' }}>
                            <RuleTrace evaluations={record.evaluations ?? []} reason={record.reason} />
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  )
}

function RuleTrace({ evaluations, reason }: { evaluations: WAFRuleEvaluation[]; reason?: string }) {
  if (!evaluations.length) return <p className="muted small" style={{ margin: 8 }}>No rule trace recorded.</p>
  return (
    <div style={{ padding: '10px 4px' }}>
      {reason ? <p className="small" style={{ margin: '0 0 8px' }}><strong>Decision:</strong> {reason}</p> : null}
      <div className="stack-list">
        {evaluations.map((e, i) => (
          <div key={`${e.rule_type}-${i}`} className="alert-row">
            <div style={{ minWidth: 0 }}>
              <strong>{RULE_TYPE_LABELS[e.rule_type] ?? e.rule_type}</strong>
              <p className="muted small" style={{ margin: '2px 0 0' }}>{e.detail}</p>
            </div>
            <span className={`badge ${e.passed ? 'status-green' : 'status-red'}`}>{e.passed ? 'pass' : 'TRIPPED'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ----------------------------- Acceptance ----------------------------- */

function AcceptanceTab() {
  const run = useWAFAcceptance()
  const report = run.data

  return (
    <>
      <Callout>
        Runs the PS-5.1 success criteria as live, evidenced checks. Each criterion executes an adversarial scenario in an
        isolated in-memory firewall (no effect on live data) and reports expected vs. actual disposition with the full
        rule trace.
      </Callout>

      <Panel
        title="PS-5.1 acceptance battery"
        icon={<IconShield width={18} height={18} />}
        action={
          <button type="button" className="btn primary" onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending ? 'Running…' : 'Run acceptance suite'}
          </button>
        }
      >
        {run.isError ? <ErrorState>Failed to run suite: {run.error.message}</ErrorState> : null}
        {!report && !run.isPending ? (
          <EmptyState title="Suite not run yet" hint="Click ‘Run acceptance suite’ to prove every PS-5.1 criterion on demand." />
        ) : null}

        {report ? (
          <>
            <div className="alert-row" style={{ marginBottom: 12 }}>
              <div>
                <strong>{report.suite}</strong>
                <p className="muted small" style={{ margin: '2px 0 0' }}>
                  {report.summary.passed}/{report.summary.total} criteria passing
                </p>
              </div>
              <span className={`badge ${report.passed ? 'status-green' : 'status-red'}`}>
                {report.passed ? 'ALL PASS' : `${report.summary.failed} FAILED`}
              </span>
            </div>

            <div className="stack-list">
              {report.criteria.map((c) => (
                <div key={c.id} className="panel" style={{ padding: 14 }}>
                  <div className="alert-row" style={{ alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 0 }}>
                      <strong>{c.ps_criterion}</strong>
                      <p className="muted small" style={{ margin: '4px 0 0' }}>{c.scenario}</p>
                    </div>
                    <span className={`badge ${c.passed ? 'status-green' : 'status-red'}`}>
                      {c.passed ? '✓ pass' : '✗ fail'}
                    </span>
                  </div>
                  <p className="small" style={{ margin: '8px 0 0' }}>
                    <span className="muted">expected</span> <code>{c.expected}</code>{' '}
                    <span className="muted">· actual</span> <code>{c.actual}</code>
                  </p>
                  {c.evidence?.trace?.length ? (
                    <details style={{ marginTop: 8 }}>
                      <summary className="small muted" style={{ cursor: 'pointer' }}>Rule trace &amp; evidence</summary>
                      <RuleTrace evaluations={c.evidence.trace} reason={c.evidence.reason} />
                    </details>
                  ) : null}
                </div>
              ))}
            </div>
          </>
        ) : null}
      </Panel>
    </>
  )
}

/* ----------------------------- Ruleset ----------------------------- */

function RulesetTab({ agentId }: { agentId?: string }) {
  const config = useWAFConfig(agentId)
  const cfg = config.data

  if (config.isLoading) return <LoadingState label="Loading effective ruleset…" />
  if (config.isError || !cfg) return <ErrorState>Failed to load WAF config.</ErrorState>

  return (
    <>
      <Callout>
        The effective ruleset the firewall will enforce{' '}
        {cfg.agent_id ? <>for agent <code>{cfg.agent_id}</code></> : 'for unregistered agents'} — resolved from{' '}
        <strong>{cfg.source === 'agent_registry' ? 'the agent registry' : 'platform defaults'}</strong>. Rate limits
        tighten automatically with the agent's risk tier.
      </Callout>

      <div className="two-column">
        <Panel title="Rate limits" icon={<IconFirewall width={18} height={18} />}>
          <p className="muted small" style={{ marginTop: 0 }}>Sliding window: {cfg.rate_window_seconds}s</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Tool</th><th>Max / window</th></tr></thead>
              <tbody>
                {Object.entries(cfg.rate_limits).map(([tool, limit]) => (
                  <tr key={tool}><td>{tool}</td><td className="mono">{limit}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Sequence rules" icon={<IconShield width={18} height={18} />}>
          {Object.keys(cfg.sequence_rules).length ? (
            <div className="stack-list">
              {Object.entries(cfg.sequence_rules).map(([tool, prereqs]) => (
                <div key={tool} className="alert-row">
                  <span><code>{tool}</code></span>
                  <span className="small muted">requires {prereqs.map((p) => <code key={p}>{p}</code>)}</span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No sequence rules" />
          )}
        </Panel>
      </div>

      <div className="two-column">
        <Panel title="Parameter validation" icon={<IconBolt width={18} height={18} />}>
          <p className="small"><span className="muted">Max payload:</span> <code>{cfg.max_param_size.toLocaleString()} bytes</code></p>
          <p className="small muted" style={{ marginBottom: 4 }}>Injection patterns</p>
          <div className="stack-list">
            {cfg.injection_patterns.map((p, i) => (
              <code key={i} className="small" style={{ display: 'block', wordBreak: 'break-all' }}>{p}</code>
            ))}
          </div>
          {cfg.param_blocklist.length ? (
            <>
              <p className="small muted" style={{ margin: '10px 0 4px' }}>Custom blocklist</p>
              {cfg.param_blocklist.map((p, i) => <code key={i} className="small" style={{ display: 'block' }}>{p}</code>)}
            </>
          ) : null}
        </Panel>

        <Panel title="Scope" icon={<IconShield width={18} height={18} />}>
          <p className="small muted" style={{ marginBottom: 4 }}>Allowed tools</p>
          {cfg.allowed_tools.length ? (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {cfg.allowed_tools.map((t) => <span key={t} className="badge status-green">{t}</span>)}
            </div>
          ) : <p className="small muted">Any (no agent-declared tool scope)</p>}
          <p className="small muted" style={{ margin: '10px 0 4px' }}>Allowed datasets</p>
          {cfg.allowed_datasets.length ? (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {cfg.allowed_datasets.map((d) => <span key={d} className="badge">{d}</span>)}
            </div>
          ) : <p className="small muted">Unrestricted</p>}
        </Panel>
      </div>
    </>
  )
}

