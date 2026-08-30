import type { ReactNode } from 'react'
import { IconInbox, IconInfo } from './icons'

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: ReactNode
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2>{title}</h2>
        {subtitle ? <p className="muted" style={{ maxWidth: 720, marginTop: 6 }}>{subtitle}</p> : null}
      </div>
      {actions ? <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>{actions}</div> : null}
    </header>
  )
}

export function Panel({
  title,
  icon,
  action,
  children,
  className = '',
}: {
  title?: ReactNode
  icon?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <article className={`panel ${className}`}>
      {title ? (
        <div className="panel-header">
          <h3 className="with-icon">
            {icon}
            {title}
          </h3>
          {action}
        </div>
      ) : null}
      {children}
    </article>
  )
}

export function Kpi({
  icon,
  label,
  value,
  hint,
  delta,
}: {
  icon?: ReactNode
  label: string
  value: ReactNode
  hint?: ReactNode
  delta?: { dir: 'up' | 'down'; text: string }
}) {
  return (
    <article className="panel kpi-card">
      <div className="kpi-top">
        <span className="kpi-label">{label}</span>
        {icon ? <span className="kpi-icon">{icon}</span> : null}
      </div>
      <strong className="kpi-value">{value}</strong>
      {delta ? (
        <span className={`kpi-delta ${delta.dir}`}>{delta.text}</span>
      ) : hint ? (
        <p className="muted small" style={{ margin: 0 }}>{hint}</p>
      ) : null}
    </article>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="empty-state">
      <IconInbox width={34} height={34} />
      <strong>{title}</strong>
      {hint ? <p className="muted small" style={{ margin: 0, maxWidth: 380 }}>{hint}</p> : null}
    </div>
  )
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="page-section">
      <div className="kpi-grid">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton" style={{ height: 118 }} />
        ))}
      </div>
      <div className="skeleton" style={{ height: 260 }} />
      <p className="muted small">{label}</p>
    </div>
  )
}

export function ErrorState({ children }: { children: ReactNode }) {
  return <div className="page-state error">{children}</div>
}

export function Callout({ children, variant = 'info' }: { children: ReactNode; variant?: 'info' | 'warn' }) {
  return (
    <div className={`callout ${variant === 'warn' ? 'warn' : ''}`}>
      <IconInfo width={18} height={18} />
      <div className="small">{children}</div>
    </div>
  )
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: T; label: string }[]
  active: T
  onChange: (id: T) => void
}) {
  return (
    <div className="tabs">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          className={t.id === active ? 'tab active' : 'tab'}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function statusClass(status: string): string {
  const n = (status || '').toLowerCase()
  if (n.includes('red') || n.includes('suspend') || n.includes('deny') || n.includes('block') || n.includes('critical') || n.includes('high')) return 'status-red'
  if (n.includes('amber') || n.includes('review') || n.includes('shadow') || n.includes('warn') || n.includes('medium') || n.includes('hitl')) return 'status-amber'
  return 'status-green'
}

export function riskClass(score: number): string {
  if (score >= 75) return 'status-red'
  if (score >= 40) return 'status-amber'
  return 'status-green'
}
