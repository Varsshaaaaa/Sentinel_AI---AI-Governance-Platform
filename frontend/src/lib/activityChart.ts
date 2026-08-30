import type { EventItem, ViolationItem, WAFRecord } from './types'

export type ActivityCategory = 'waf' | 'violations' | 'policy' | 'governance'

export type ActivityChartRow = {
  time: string
  waf: number
  violations: number
  policy: number
  governance: number
}

export type ActivityChartPoint = {
  id: string
  timestamp: string
  category: ActivityCategory
}

type BuildParams = {
  range: '30m' | '1h' | '24h'
  timelineEvents: EventItem[]
  actionLogEvents: EventItem[]
  violations: ViolationItem[]
  wafRecords: WAFRecord[]
  now?: number
}

const RANGE_MS: Record<BuildParams['range'], number> = {
  '30m': 30 * 60_000,
  '1h': 60 * 60_000,
  '24h': 24 * 60 * 60_000,
}

const BUCKET_MS: Record<BuildParams['range'], number> = {
  '30m': 5 * 60_000,
  '1h': 5 * 60_000,
  '24h': 60 * 60_000,
}

function timelineCategory(eventType: string): ActivityCategory | null {
  switch (eventType) {
    case 'ViolationDetected':
      // Violations come from the violations store (complete history).
      return null
    case 'ToolCalled':
      // WAF intercepts come from WAF records (one row per intercept).
      return null
    case 'PolicyMatched':
    case 'PolicyUpdated':
      return 'policy'
    default:
      return 'governance'
  }
}

function bucketKey(timestamp: string, bucketMs: number): string {
  const t = new Date(timestamp).getTime()
  return new Date(Math.floor(t / bucketMs) * bucketMs).toISOString()
}

function inWindow(timestamp: string, windowStart: number, now: number): boolean {
  const t = new Date(timestamp).getTime()
  return t >= windowStart && t <= now
}

/** Merge timeline + action log, deduped by event_id or timestamp+type. */
export function mergeGovernanceEvents(
  timelineEvents: EventItem[],
  actionLogEvents: EventItem[],
): EventItem[] {
  const seen = new Set<string>()
  const merged: EventItem[] = []
  for (const event of [...timelineEvents, ...actionLogEvents]) {
    const id = event.event_id ?? `${event.timestamp}|${event.event_type}|${event.agent_id ?? ''}`
    if (seen.has(id)) continue
    seen.add(id)
    merged.push(event)
  }
  return merged
}

/** Build chart rows from authoritative per-category sources (no double counting). */
export function buildActivityChartData({
  range,
  timelineEvents,
  actionLogEvents,
  violations,
  wafRecords,
  now = Date.now(),
}: BuildParams): { rows: ActivityChartRow[]; points: ActivityChartPoint[] } {
  const windowMs = RANGE_MS[range]
  const bucketMs = BUCKET_MS[range]
  const windowStart = now - windowMs

  const points: ActivityChartPoint[] = []

  for (const record of wafRecords) {
    if (!inWindow(record.timestamp, windowStart, now)) continue
    points.push({
      id: record.record_id,
      timestamp: record.timestamp,
      category: 'waf',
    })
  }

  for (const violation of violations) {
    if (!inWindow(violation.timestamp, windowStart, now)) continue
    points.push({
      id: violation.violation_id,
      timestamp: violation.timestamp,
      category: 'violations',
    })
  }

  for (const event of mergeGovernanceEvents(timelineEvents, actionLogEvents)) {
    if (!inWindow(event.timestamp, windowStart, now)) continue
    const category = timelineCategory(event.event_type)
    if (!category) continue
    points.push({
      id: event.event_id ?? `${event.timestamp}|${event.event_type}|${event.agent_id ?? ''}`,
      timestamp: event.timestamp,
      category,
    })
  }

  const alignedStart = Math.floor(windowStart / bucketMs) * bucketMs
  const buckets = new Map<string, ActivityChartRow>()
  for (let t = alignedStart; t <= now; t += bucketMs) {
    const key = new Date(t).toISOString()
    buckets.set(key, { time: key, waf: 0, violations: 0, policy: 0, governance: 0 })
  }

  for (const point of points) {
    const key = bucketKey(point.timestamp, bucketMs)
    const row = buckets.get(key)
    if (!row) continue
    row[point.category] += 1
  }

  return {
    rows: [...buckets.values()].sort((a, b) => a.time.localeCompare(b.time)),
    points,
  }
}

export function activityTotals(rows: ActivityChartRow[]) {
  return rows.reduce(
    (acc, row) => ({
      waf: acc.waf + row.waf,
      violations: acc.violations + row.violations,
      policy: acc.policy + row.policy,
      governance: acc.governance + row.governance,
    }),
    { waf: 0, violations: 0, policy: 0, governance: 0 },
  )
}
