import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { useGraph, useOrphanAgents } from '../lib/api'
import type { GraphEdge, GraphNode } from '../lib/types'
import { EmptyState, ErrorState, Kpi, LoadingState, Panel, PageHeader } from '../components/ui'
import { IconGraph, IconRobot, IconInfo } from '../components/icons'

// --- Visual vocabulary ----------------------------------------------------

type TypeStyle = { color: string; glyph: string; blurb: string }

const TYPE_STYLE: Record<string, TypeStyle> = {
  User: { color: '#8b5cf6', glyph: '👤', blurb: 'Owner / team accountable for the agent' },
  Agent: { color: '#6d28d9', glyph: '🤖', blurb: 'Autonomous AI agent under governance' },
  Model: { color: '#f59e0b', glyph: '🧠', blurb: 'Foundation model the agent calls' },
  Tool: { color: '#10b981', glyph: '🔧', blurb: 'Tool / function the agent can invoke' },
  DataSource: { color: '#ef4444', glyph: '🗄️', blurb: 'Dataset or system the agent can reach' },
  Policy: { color: '#3b82f6', glyph: '📜', blurb: 'Governance policy bound to the agent' },
}

const EDGE_STYLE: Record<string, { color: string; label: string; animated?: boolean }> = {
  OWNS: { color: '#8b5cf6', label: 'owns' },
  USES_MODEL: { color: '#f59e0b', label: 'uses model' },
  USES: { color: '#10b981', label: 'can use' },
  CALLS: { color: '#059669', label: 'called', animated: true },
  CONNECTED_TO: { color: '#ef4444', label: 'reads' },
  HAS_POLICY: { color: '#3b82f6', label: 'governed by' },
  DEPLOYS: { color: '#64748b', label: 'deploys' },
}

// Left-to-right column order: accountability → agent → what it touches → governance.
const COLUMN_ORDER = ['User', 'Agent', 'Model', 'Tool', 'DataSource', 'Policy']
const COL_WIDTH = 300
const ROW_HEIGHT = 132

function fallbackStyle(type: string): TypeStyle {
  return TYPE_STYLE[type] ?? { color: '#94a3b8', glyph: '•', blurb: type }
}

// --- Custom node ----------------------------------------------------------

type GovNodeData = {
  label: string
  nodeType: string
  detail?: string
  badge?: string
  dimmed?: boolean
  selected?: boolean
}

function GovNode({ data }: NodeProps<GovNodeData>) {
  const style = fallbackStyle(data.nodeType)
  return (
    <div
      className="gov-node"
      style={{
        opacity: data.dimmed ? 0.28 : 1,
        borderColor: data.selected ? style.color : 'var(--line)',
        boxShadow: data.selected
          ? `0 0 0 2px ${style.color}, 0 10px 24px -12px rgba(15,23,42,0.35)`
          : '0 4px 14px -8px rgba(15,23,42,0.25)',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div className="gov-node-accent" style={{ background: style.color }} />
      <div className="gov-node-body">
        <div className="gov-node-head">
          <span className="gov-node-glyph" style={{ background: `${style.color}1a`, color: style.color }}>
            {style.glyph}
          </span>
          <span className="gov-node-type" style={{ color: style.color }}>{data.nodeType}</span>
          {data.badge ? <span className="gov-node-badge">{data.badge}</span> : null}
        </div>
        <div className="gov-node-label">{data.label}</div>
        {data.detail ? <div className="gov-node-detail">{data.detail}</div> : null}
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  )
}

const nodeTypes = { gov: GovNode }

// --- Layout ---------------------------------------------------------------

function detailFor(node: GraphNode): string | undefined {
  const p = node.properties ?? {}
  switch (node.node_type) {
    case 'Agent':
      return [p.framework, p.status].filter(Boolean).join(' · ') || undefined
    case 'Model':
      return (p.provider as string) || undefined
    case 'Tool': {
      const ops = p.operations as string[] | undefined
      return ops?.length ? ops.join(', ') : undefined
    }
    case 'User':
      return (p.team as string) || undefined
    case 'Policy': {
      const rc = p.rule_count as number | undefined
      return rc != null ? `${rc} rule${rc === 1 ? '' : 's'}` : undefined
    }
    default:
      return undefined
  }
}

function badgeFor(node: GraphNode): string | undefined {
  if (node.node_type === 'Agent') {
    const tier = node.properties?.risk_tier as string | undefined
    return tier ? `${tier} risk` : undefined
  }
  return undefined
}

export function GraphPage() {
  const queryClient = useQueryClient()
  const graph = useGraph()
  const orphanAgents = useOrphanAgents()
  const [selected, setSelected] = useState<string | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)

  // Focus follows a click (sticky) or a hover (transient). Everything else
  // stays visually calm so a dense graph stays readable.
  const focusId = selected ?? hovered

  const rawNodes = graph.data?.nodes ?? []
  const rawEdges = graph.data?.edges ?? []

  const orphanIds = useMemo(
    () => new Set((orphanAgents.data?.nodes ?? []).map((n) => n.node_id)),
    [orphanAgents.data],
  )

  // Adjacency for highlight + detail panel.
  const neighborsOf = useMemo(() => {
    const map = new Map<string, Set<string>>()
    const add = (a: string, b: string) => {
      if (!map.has(a)) map.set(a, new Set())
      map.get(a)!.add(b)
    }
    for (const e of rawEdges) {
      add(e.source_id, e.target_id)
      add(e.target_id, e.source_id)
    }
    return map
  }, [rawEdges])

  const activeSet = useMemo(() => {
    if (!focusId) return null
    const set = new Set<string>([focusId])
    neighborsOf.get(focusId)?.forEach((n) => set.add(n))
    return set
  }, [focusId, neighborsOf])

  const flowNodes = useMemo<Node<GovNodeData>[]>(() => {
    const columns: Record<string, GraphNode[]> = {}
    for (const n of rawNodes) {
      const key = COLUMN_ORDER.includes(n.node_type) ? n.node_type : 'DataSource'
      ;(columns[key] ??= []).push(n)
    }
    for (const key of Object.keys(columns)) {
      columns[key].sort((a, b) => a.label.localeCompare(b.label))
    }

    const tallest = Math.max(1, ...COLUMN_ORDER.map((c) => columns[c]?.length ?? 0))
    const canvasHeight = tallest * ROW_HEIGHT

    const nodes: Node<GovNodeData>[] = []
    COLUMN_ORDER.forEach((type, colIndex) => {
      const items = columns[type] ?? []
      const offset = (canvasHeight - items.length * ROW_HEIGHT) / 2
      items.forEach((node, rowIndex) => {
        const isOrphan = orphanIds.has(node.node_id)
        nodes.push({
          id: node.node_id,
          type: 'gov',
          position: { x: colIndex * COL_WIDTH, y: offset + rowIndex * ROW_HEIGHT },
          data: {
            label: node.label,
            nodeType: node.node_type,
            detail: detailFor(node),
            badge: isOrphan ? 'orphan' : badgeFor(node),
            dimmed: activeSet ? !activeSet.has(node.node_id) : false,
            selected: focusId === node.node_id,
          },
          draggable: true,
        })
      })
    })
    return nodes
  }, [rawNodes, orphanIds, activeSet, focusId])

  const flowEdges = useMemo<Edge[]>(() => {
    return rawEdges.map((edge, index) => {
      const style = EDGE_STYLE[edge.edge_type] ?? { color: '#cbd5e1', label: edge.edge_type }
      // Is this edge part of the focused node's connections?
      const focused = activeSet
        ? activeSet.has(edge.source_id) && activeSet.has(edge.target_id)
        : false
      // At rest (nothing focused) lines are calm and label-free; on focus the
      // relevant edges brighten, thicken, animate, and reveal their label.
      const restOpacity = 0.22
      return {
        id: `${edge.source_id}-${edge.target_id}-${edge.edge_type}-${index}`,
        source: edge.source_id,
        target: edge.target_id,
        type: 'smoothstep',
        label: focused ? style.label : undefined,
        animated: Boolean(style.animated) && focused,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: style.color,
        },
        style: {
          stroke: style.color,
          strokeWidth: focused ? 2.2 : 1.2,
          opacity: activeSet ? (focused ? 1 : 0.06) : restOpacity,
        },
        labelStyle: { fill: style.color, fontSize: 10, fontWeight: 700 },
        labelShowBg: true,
        labelBgStyle: { fill: '#ffffff', fillOpacity: 0.92 },
        labelBgPadding: [5, 2] as [number, number],
        labelBgBorderRadius: 5,
        zIndex: focused ? 10 : 0,
      }
    })
  }, [rawEdges, activeSet])

  const nodeTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const node of rawNodes) counts[node.node_type] = (counts[node.node_type] ?? 0) + 1
    return counts
  }, [rawNodes])

  const selectedNode = useMemo<GraphNode | null>(
    () => rawNodes.find((n) => n.node_id === selected) ?? null,
    [rawNodes, selected],
  )

  const selectedNeighbors = useMemo(() => {
    if (!selected) return []
    const rows: { node: GraphNode; edge: GraphEdge; direction: 'out' | 'in' }[] = []
    for (const e of rawEdges) {
      if (e.source_id === selected) {
        const node = rawNodes.find((n) => n.node_id === e.target_id)
        if (node) rows.push({ node, edge: e, direction: 'out' })
      } else if (e.target_id === selected) {
        const node = rawNodes.find((n) => n.node_id === e.source_id)
        if (node) rows.push({ node, edge: e, direction: 'in' })
      }
    }
    return rows
  }, [selected, rawEdges, rawNodes])

  function refreshGraph() {
    void queryClient.invalidateQueries({ queryKey: ['graph'] })
  }

  if (graph.isLoading) return <LoadingState label="Loading governance graph…" />
  if (graph.isError || !graph.data) return <ErrorState>Unable to load governance graph.</ErrorState>
  if (!rawNodes.length) {
    return (
      <section className="page-section">
        <PageHeader
          eyebrow={<><IconGraph width={13} height={13} /> PS-1.3 · Governance Graph</>}
          title="Governance Graph"
          subtitle="No graph nodes yet. Register agents and run tool intercepts to populate the dependency map."
        />
        <EmptyState title="Graph is empty" hint="Seed demo data or register agents to build the governance graph." />
      </section>
    )
  }

  return (
    <section className="page-section">
      <PageHeader
        eyebrow={<><IconGraph width={13} height={13} /> PS-1.3 · Governance Graph</>}
        title="Governance Graph"
        subtitle="Read it left to right: every owner is accountable for an agent, each agent uses models & tools and reaches data sources, and policies bind to agents. Hover a node to preview its links, click to pin the blast radius, and spot ungoverned (orphan) agents."
      />

      <div className="kpi-grid">
        <Kpi label="Nodes" value={rawNodes.length} icon={<IconGraph width={16} height={16} />} />
        <Kpi label="Relationships" value={rawEdges.length} />
        <Kpi label="Agents" value={nodeTypeCounts.Agent ?? 0} icon={<IconRobot width={16} height={16} />} />
        <Kpi label="Orphan agents" value={orphanAgents.data?.nodes.length ?? 0} hint="No policy / owner linkage" />
      </div>

      <Panel
        title="Dependency graph"
        icon={<IconGraph width={18} height={18} />}
        action={
          <div className="row-gap">
            {selected ? (
              <button type="button" className="btn sm ghost" onClick={() => setSelected(null)}>Clear focus</button>
            ) : null}
            <button type="button" className="btn sm" onClick={refreshGraph}>Refresh</button>
          </div>
        }
      >
        <div className="graph-split">
          <div className="reactflow-wrap graph-canvas">
            <ReactFlow
              fitView
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              minZoom={0.2}
              onNodeClick={(_, node) => setSelected((cur) => (cur === node.id ? null : node.id))}
              onNodeMouseEnter={(_, node) => setHovered(node.id)}
              onNodeMouseLeave={() => setHovered(null)}
              onPaneClick={() => setSelected(null)}
              proOptions={{ hideAttribution: true }}
              defaultEdgeOptions={{ type: 'smoothstep' }}
            >
              <MiniMap
                pannable
                zoomable
                nodeColor={(n) => fallbackStyle((n.data as GovNodeData)?.nodeType ?? '').color}
              />
              <Controls />
              <Background color="#dbe1ea" gap={22} />
            </ReactFlow>
          </div>

          <aside className="graph-detail">
            {selectedNode ? (
              <>
                <div className="graph-detail-head">
                  <span
                    className="gov-node-glyph"
                    style={{
                      background: `${fallbackStyle(selectedNode.node_type).color}1a`,
                      color: fallbackStyle(selectedNode.node_type).color,
                    }}
                  >
                    {fallbackStyle(selectedNode.node_type).glyph}
                  </span>
                  <div>
                    <div className="graph-detail-title">{selectedNode.label}</div>
                    <div className="muted small">{selectedNode.node_type}</div>
                  </div>
                </div>
                {orphanIds.has(selectedNode.node_id) ? (
                  <div className="graph-detail-warn">
                    <IconInfo width={13} height={13} /> Ungoverned — no policy bound to this agent.
                  </div>
                ) : null}

                {Object.keys(selectedNode.properties ?? {}).length ? (
                  <div className="graph-prop-list">
                    {Object.entries(selectedNode.properties).map(([k, v]) => (
                      <div key={k} className="graph-prop-row">
                        <span className="muted small">{k}</span>
                        <span className="small">{Array.isArray(v) ? v.join(', ') : String(v)}</span>
                      </div>
                    ))}
                  </div>
                ) : null}

                <div className="graph-detail-sub">
                  Connections · {selectedNeighbors.length}
                </div>
                <div className="stack-list compact">
                  {selectedNeighbors.map(({ node, edge, direction }, i) => {
                    const es = EDGE_STYLE[edge.edge_type] ?? { color: '#94a3b8', label: edge.edge_type }
                    return (
                      <button
                        key={`${node.node_id}-${i}`}
                        type="button"
                        className="list-row graph-neighbor"
                        onClick={() => setSelected(node.node_id)}
                      >
                        <span className="graph-neighbor-main">
                          <span className="gov-node-glyph sm" style={{ color: fallbackStyle(node.node_type).color }}>
                            {fallbackStyle(node.node_type).glyph}
                          </span>
                          {node.label}
                        </span>
                        <span className="badge" style={{ color: es.color, borderColor: `${es.color}44` }}>
                          {direction === 'out' ? es.label : `${es.label} ←`}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </>
            ) : (
              <div className="graph-detail-empty">
                <IconInfo width={16} height={16} />
                <p className="muted small">Hover any node to light up its connections, or click to pin it here and inspect properties + every linked agent, model, tool, data source, and policy.</p>
                <div className="graph-legend-block">
                  <div className="graph-legend-title">Node types</div>
                  {COLUMN_ORDER.map((type) => (
                    <div key={type} className="legend-item">
                      <span className="legend-dot" style={{ backgroundColor: fallbackStyle(type).color }} />
                      <span>{type}{nodeTypeCounts[type] ? ` · ${nodeTypeCounts[type]}` : ''}</span>
                    </div>
                  ))}
                  <div className="graph-legend-title">Relationships</div>
                  {Object.entries(EDGE_STYLE)
                    .filter(([t]) => rawEdges.some((e) => e.edge_type === t))
                    .map(([type, s]) => (
                      <div key={type} className="legend-item">
                        <span className="legend-line" style={{ backgroundColor: s.color }} />
                        <span>{s.label}</span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </aside>
        </div>
      </Panel>

      <Panel title="Orphan agents" icon={<IconRobot width={18} height={18} />} action={<span className="muted small">Agents missing a policy or owner</span>}>
        {orphanAgents.data?.nodes.length ? (
          <div className="stack-list compact">
            {orphanAgents.data.nodes.map((node) => (
              <button
                key={node.node_id}
                type="button"
                className="list-row graph-neighbor"
                onClick={() => setSelected(node.node_id)}
              >
                <span>{node.label}</span>
                <span className="badge status-amber">orphan</span>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState title="No orphan agents" hint="Every agent is linked to a policy and owner in the current graph." />
        )}
      </Panel>
    </section>
  )
}
