import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Line,
  LineChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from 'recharts'
import {
  useAgents,
  useDashboard,
  useGovernanceActionLog,
  useGovernanceTimeline,
  useHitlTickets,
  usePolicies,
  useViolations,
  useWAFRecords,
  useWAFStats,
  LIVE_REFETCH_MS,
} from '../lib/api'
import { activityTotals, buildActivityChartData } from '../lib/activityChart'
import { AnalyticsToolbar, ToolbarSelect } from '../components/AnalyticsToolbar'
import { ErrorState, LoadingState } from '../components/ui'
import {
  IconActivity,
  IconAlert,
  IconFirewall,
  IconGrid,
  IconRobot,
  IconScroll,
  IconShield,
  IconUsersCheck,
} from '../components/icons'

const CHART_COLORS = ['#6d28d9', '#3b82f6', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6']

function fmtNum(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function TrendBadge({ value, invert }: { value: number; invert?: boolean }) {
  if (value === 0) return <span className="db-tile-trend">—</span>
  const up = value > 0
  const good = invert ? !up : up
  return (
    <span className={`db-tile-trend${good ? ' down' : ' up'}`}>
      {up ? '↑' : '↓'} {Math.abs(value)}%
    </span>
  )
}

export function DashboardPage() {
  const navigate = useNavigate()
  const [range, setRange] = useState('24h')
  const [lastRefresh, setLastRefresh] = useState(() => new Date().toLocaleTimeString())

  const timelineLimit = range === '24h' ? 500 : 250
  const dashboard = useDashboard()
  const timeline = useGovernanceTimeline(undefined, timelineLimit)
  const actionLog = useGovernanceActionLog(undefined, 100)
  const wafStats = useWAFStats()
  const wafRecords = useWAFRecords(undefined, 500)
  const hitl = useHitlTickets('pending')
  const violations = useViolations()
  const agents = useAgents()
  const policies = usePolicies()

  const refresh = () => {
    void dashboard.refetch()
    void timeline.refetch()
    void actionLog.refetch()
    void wafStats.refetch()
    void wafRecords.refetch()
    void hitl.refetch()
    void violations.refetch()
    setLastRefresh(new Date().toLocaleTimeString())
  }

  const { chartData, chartTotals, hasActivityInWindow } = useMemo(() => {
    const rangeKey = range as '30m' | '1h' | '24h'
    const { rows, points } = buildActivityChartData({
      range: rangeKey,
      timelineEvents: timeline.data?.events ?? [],
      actionLogEvents: actionLog.data?.actions ?? [],
      violations: violations.data?.violations ?? [],
      wafRecords: wafRecords.data?.records ?? [],
    })
    const totals = activityTotals(rows)
    return {
      chartData: rows,
      chartTotals: totals,
      hasActivityInWindow: points.length > 0,
    }
  }, [timeline.data, actionLog.data, violations.data, wafRecords.data, range])

  if (dashboard.isLoading) return <LoadingState label="Loading dashboard…" />
  if (dashboard.isError || !dashboard.data) {
    return (
      <div className="db-page">
        <ErrorState>Failed to load dashboard. Verify the backend is running on <code>localhost:8080</code>.</ErrorState>
      </div>
    )
  }

  const { summary } = dashboard.data
  const totalWaf = wafStats.data?.total_calls ?? 0
  const denied = wafStats.data?.denied ?? 0
  const denyPct = totalWaf > 0 ? Math.round((denied / totalWaf) * 100) : 0
  const pendingHitl = hitl.data?.tickets.length ?? 0
  const violCount = violations.data?.violations.length ?? summary.total_violations
  const greenPct = summary.total_agents > 0
    ? Math.round((summary.compliance_green / summary.total_agents) * 100)
    : 100

  const agentList = agents.data?.agents ?? []
  const policyList = policies.data?.policies ?? []
  const recentBlocks = wafStats.data?.recent_blocks ?? []
  const govEvents = [
    ...(timeline.data?.events ?? []).slice(0, 8),
    ...(actionLog.data?.actions ?? []).slice(0, 4),
  ].slice(0, 8)

  return (
    <div className="db-page">
      <AnalyticsToolbar onRefresh={refresh} refreshing={dashboard.isFetching} lastRefresh={lastRefresh}>
        <ToolbarSelect
          label="Time range"
          value={range}
          onChange={setRange}
          options={[
            { value: '30m', label: 'Past 30 minutes' },
            { value: '1h', label: 'Past hour' },
            { value: '24h', label: 'Past 24 hours' },
          ]}
        />
        <span className="db-refresh-label">Auto-refresh {LIVE_REFETCH_MS / 1000}s</span>
      </AnalyticsToolbar>

      <div className="db-tiles">
        <button type="button" className="db-tile db-tile-waf" onClick={() => navigate('/waf')}>
          <span className="db-tile-icon db-icon-waf"><IconFirewall width={16} height={16} /></span>
          <div className="db-tile-corners">
            <span>{summary.active_agents} agents</span>
            <span>{denyPct}% denied</span>
          </div>
          <span className="db-tile-big">{fmtNum(totalWaf)}</span>
          <span className="db-tile-unit">tool intercepts</span>
          <TrendBadge value={denyPct} invert />
        </button>

        <button type="button" className="db-tile db-tile-viol" onClick={() => navigate('/violations')}>
          <span className="db-tile-icon db-icon-viol"><IconAlert width={16} height={16} /></span>
          <div className="db-tile-corners">
            <span>{summary.total_violations} total</span>
          </div>
          <span className="db-tile-big">{violCount}</span>
          <span className="db-tile-unit">violations</span>
          <TrendBadge value={violCount > 0 ? 12 : 0} invert />
        </button>

        <button type="button" className="db-tile db-tile-hitl" onClick={() => navigate('/hitl')}>
          <span className="db-tile-icon db-icon-hitl"><IconUsersCheck width={16} height={16} /></span>
          <div className="db-tile-corners">
            <span>awaiting review</span>
          </div>
          <span className="db-tile-big">{pendingHitl}</span>
          <span className="db-tile-unit">HITL pending</span>
        </button>

        <button type="button" className="db-tile db-tile-comp" onClick={() => navigate('/observability')}>
          <span className="db-tile-icon db-icon-comp"><IconShield width={16} height={16} /></span>
          <div className="db-tile-corners">
            <span>{summary.compliance_green} green</span>
            <span>{summary.compliance_red} red</span>
          </div>
          <span className="db-tile-big">{greenPct}%</span>
          <span className="db-tile-unit">compliant</span>
          <TrendBadge value={greenPct >= 80 ? 5 : -8} />
        </button>
      </div>

      <section className="db-chart-section">
        <div className="db-chart-header">
          <h2 className="db-chart-title">
            <IconActivity width={16} height={16} />
            Governance activity
          </h2>
          <button type="button" className="btn sm" onClick={() => navigate('/observability')}>View events</button>
        </div>
        <div className="db-chart-body">
          {!hasActivityInWindow ? (
            <div className="db-chart-empty">
              {range !== '24h'
                ? 'No activity in this window. Try “Past 24 hours” to see the full run history.'
                : 'No governance activity recorded yet.'}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS[0]} strokeOpacity={0.08} />
                <XAxis
                  dataKey="time"
                  tickFormatter={(v) => {
                    const d = new Date(v)
                    return range === '24h'
                      ? d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit' })
                      : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                  }}
                  tick={{ fill: '#8e8ea4', fontSize: 11 }}
                />
                <YAxis tick={{ fill: '#8e8ea4', fontSize: 11 }} allowDecimals={false} />
                <Tooltip
                  labelFormatter={(v) => new Date(String(v)).toLocaleString()}
                  contentStyle={{ background: '#fff', border: '1px solid rgba(0,0,0,0.08)', borderRadius: 8, fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="waf" name={`WAF intercepts (${chartTotals.waf})`} stroke={CHART_COLORS[1]} dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="violations" name={`Violations (${chartTotals.violations})`} stroke={CHART_COLORS[3]} dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="policy" name={`Policy (${chartTotals.policy})`} stroke={CHART_COLORS[0]} dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="governance" name={`Governance (${chartTotals.governance})`} stroke={CHART_COLORS[4]} dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      <div className="db-list-tiles">
        <div className="db-list-tile" onClick={() => navigate('/agents')} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && navigate('/agents')}>
          <div className="db-list-tile-header">
            <IconRobot width={16} height={16} />
            <h3>Agents</h3>
            <span className="db-list-tile-count">{agentList.length}</span>
          </div>
          <ul className="db-list-tile-items">
            {agentList.length === 0 ? (
              <li className="db-list-tile-empty">No agents registered</li>
            ) : (
              agentList.slice(0, 8).map((a) => (
                <li key={a.agent_id}>{a.name || a.agent_id}</li>
              ))
            )}
            {agentList.length > 8 ? <li className="db-list-tile-more">+{agentList.length - 8} more</li> : null}
          </ul>
        </div>

        <div className="db-list-tile" onClick={() => navigate('/policies')} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && navigate('/policies')}>
          <div className="db-list-tile-header">
            <IconScroll width={16} height={16} />
            <h3>Policies</h3>
            <span className="db-list-tile-count">{policyList.length}</span>
          </div>
          <ul className="db-list-tile-items">
            {policyList.length === 0 ? (
              <li className="db-list-tile-empty">No policies deployed</li>
            ) : (
              policyList.slice(0, 8).map((p) => (
                <li key={p.policy_id}>{p.name}</li>
              ))
            )}
            {policyList.length > 8 ? <li className="db-list-tile-more">+{policyList.length - 8} more</li> : null}
          </ul>
        </div>

        <div className="db-list-tile" onClick={() => navigate('/waf')} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && navigate('/waf')}>
          <div className="db-list-tile-header">
            <IconFirewall width={16} height={16} />
            <h3>Recent blocks</h3>
            <span className="db-list-tile-count">{recentBlocks.length}</span>
          </div>
          <ul className="db-list-tile-items">
            {recentBlocks.length === 0 ? (
              <li className="db-list-tile-empty">No blocks recorded</li>
            ) : (
              recentBlocks.slice(0, 8).map((b) => (
                <li key={b.record_id}>{b.tool_name} · {b.disposition}</li>
              ))
            )}
          </ul>
        </div>

        <div className="db-list-tile" onClick={() => navigate('/observability')} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && navigate('/observability')}>
          <div className="db-list-tile-header">
            <IconGrid width={16} height={16} />
            <h3>Governance events</h3>
            <span className="db-list-tile-count">{govEvents.length}</span>
          </div>
          <ul className="db-list-tile-items">
            {govEvents.length === 0 ? (
              <li className="db-list-tile-empty">No events yet</li>
            ) : (
              govEvents.map((e, i) => (
                <li key={`${e.event_type}-${i}`}>{e.event_type}</li>
              ))
            )}
          </ul>
        </div>
      </div>
    </div>
  )
}
