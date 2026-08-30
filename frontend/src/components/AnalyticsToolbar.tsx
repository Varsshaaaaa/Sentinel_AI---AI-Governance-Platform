import type { ReactNode } from 'react'
import { IconRefresh } from './icons'

type Props = {
  children?: ReactNode
  onRefresh?: () => void
  refreshing?: boolean
  lastRefresh?: string
}

export function AnalyticsToolbar({ children, onRefresh, refreshing, lastRefresh }: Props) {
  return (
    <div className="db-toolbar">
      <div className="db-toolbar-left">{children}</div>
      <div className="db-toolbar-right">
        {lastRefresh ? <span className="db-refresh-label">Updated {lastRefresh}</span> : null}
        {onRefresh ? (
          <button type="button" className="icon-btn" title="Refresh" onClick={onRefresh} disabled={refreshing}>
            <IconRefresh />
          </button>
        ) : null}
      </div>
    </div>
  )
}

export function ToolbarSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label className="db-filter-wrap">
      <span className="sr-only">{label}</span>
      <select className="db-filter-select" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  )
}
