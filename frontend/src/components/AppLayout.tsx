import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAgents, useHealth, useHitlTickets, useViolations } from '../lib/api'
import { useAgent } from '../context/AgentContext'
import {
  IconActivity,
  IconAlert,
  IconFirewall,
  IconGraph,
  IconGrid,
  IconRefresh,
  IconReplay,
  IconRobot,
  IconScroll,
  IconSearch,
  IconShield,
  IconSidebar,
  IconUsersCheck,
  IconFlask,
} from './icons'

type NavItem = {
  to: string
  label: string
  icon: ReactNode
  badge?: number
}

type NavGroup = {
  label: string
  items: NavItem[]
}

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [search, setSearch] = useState('')
  const location = useLocation()
  const onAgentChat = location.pathname === '/agent-chat'

  const { agentId, setAgentId } = useAgent()
  const agents = useAgents()
  const health = useHealth()
  const hitl = useHitlTickets('pending')
  const violations = useViolations()

  const pendingHitl = hitl.data?.tickets.length ?? 0
  const openViolations = violations.data?.violations.length ?? 0

  const groups: NavGroup[] = [
    {
      label: 'Overview',
      items: [{ to: '/dashboard', label: 'Dashboard', icon: <IconGrid /> }],
    },
    {
      label: 'Inventory',
      items: [
        { to: '/agents', label: 'Agent Registry', icon: <IconRobot /> },
        { to: '/graph', label: 'Governance Graph', icon: <IconGraph /> },
      ],
    },
    {
      label: 'Enforcement',
      items: [
        { to: '/waf', label: 'Agent WAF', icon: <IconFirewall /> },
        { to: '/policies', label: 'Policy Engine', icon: <IconScroll /> },
      ],
    },
    {
      label: 'Oversight',
      items: [
        { to: '/hitl', label: 'HITL Queue', icon: <IconUsersCheck />, badge: pendingHitl },
        { to: '/violations', label: 'Violations', icon: <IconAlert />, badge: openViolations },
      ],
    },
    {
      label: 'Audit & Observability',
      items: [
        { to: '/replay', label: 'Decision Replay', icon: <IconReplay /> },
        { to: '/observability', label: 'Observability & SLA', icon: <IconActivity /> },
      ],
    },
  ]

  const filteredGroups = search.trim()
    ? groups
        .map((g) => ({
          ...g,
          items: g.items.filter((i) => i.label.toLowerCase().includes(search.trim().toLowerCase())),
        }))
        .filter((g) => g.items.length > 0)
    : groups

  const healthOk = health.isSuccess
  const healthLabel = healthOk ? 'API online' : health.isError ? 'API offline' : 'Checking…'

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        document.getElementById('portal-search')?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function refreshAll() {
    void health.refetch()
    void agents.refetch()
    void hitl.refetch()
    void violations.refetch()
  }

  return (
    <div className={`portal-layout${collapsed ? ' sidebar-collapsed' : ''}`}>
      <header className="portal-header">
        <div className="header-left">
          <button
            type="button"
            className="icon-btn header-toggle"
            aria-label="Toggle sidebar"
            onClick={() => setCollapsed((v) => !v)}
          >
            <IconSidebar />
          </button>
          <NavLink to="/dashboard" className="header-logo-link">
            <span className="header-logo-icon"><IconShield width={18} height={18} /></span>
            <span className="header-logo-text">SentinelAI</span>
          </NavLink>
          <span className="header-separator" />
          <label className="workspace-select">
            <IconRobot width={14} height={14} />
            <select
              value={agentId ?? ''}
              onChange={(e) => setAgentId(e.target.value || null)}
              aria-label="Scope to agent"
            >
              <option value="">All agents</option>
              {(agents.data?.agents ?? []).map((a) => (
                <option key={a.agent_id} value={a.agent_id}>{a.name || a.agent_id}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="header-center">
          <div className="search-bar">
            <IconSearch width={15} height={15} />
            <input
              id="portal-search"
              type="search"
              placeholder="Search navigation…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <kbd>Ctrl K</kbd>
          </div>
        </div>

        <div className="header-right">
          <NavLink
            to="/agent-chat"
            className={`test-chat-btn${onAgentChat ? ' active' : ''}`}
            title="Testing entrypoint: Cerebras agent chat backed by a dedicated chat Lambda"
          >
            <IconFlask width={15} height={15} />
            <span className="test-chat-btn-label">
              <span className="test-chat-btn-title">Test Agent Chat</span>
              <span className="test-chat-btn-sub">Testing entrypoint · Chat Lambda</span>
            </span>
          </NavLink>
          <span className={`status-chip${healthOk ? ' ok' : health.isError ? ' bad' : ''}`} title={healthLabel}>
            <span className="health-dot" />
            {healthLabel}
          </span>
          <button type="button" className="icon-btn" title="Refresh" onClick={refreshAll}>
            <IconRefresh />
          </button>
          <button type="button" className="user-btn" title="Governance admin">SA</button>
        </div>
      </header>

      <aside className={`portal-sidebar${collapsed ? ' collapsed' : ''}`}>
        <nav className="sidebar-nav">
          {filteredGroups.map((group) => (
            <div key={group.label}>
              <p className="sidebar-group-label">{group.label}</p>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  title={item.label}
                  className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}
                >
                  <span className="sidebar-item-icon">{item.icon}</span>
                  <span className="sidebar-item-label">{item.label}</span>
                  {item.badge ? <span className="sidebar-badge">{item.badge}</span> : null}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <button
          type="button"
          className="sidebar-toggle"
          onClick={() => setCollapsed((v) => !v)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <IconSidebar />
        </button>
      </aside>

      <main className="portal-content">
        <Outlet />
      </main>
    </div>
  )
}
