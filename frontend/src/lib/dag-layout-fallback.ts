// Fallback layout for old workflows that carry no source_columns.
// Isolated here to keep dag-layout.ts under 200 lines.
import dagre from '@dagrejs/dagre'
import { MarkerType, type Edge, type Node } from 'reactflow'
import { getStatusColor, STATUS_NODE_BORDER } from '@/lib/status'
import type { DAGNode } from '@/types/api'

// Mirror dag-layout.ts constants — kept in sync, not imported to avoid circular deps.
const NODE_W = 180
const NODE_H = 64

/**
 * Derivation-only dagre layout — used as graceful degradation for old
 * workflows that carry no source_columns data.
 */
export function buildDerivationOnlyLayout(dagNodes: DAGNode[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60 })

  dagNodes.forEach((n) => g.setNode(n.variable, { width: NODE_W, height: NODE_H }))
  dagNodes.forEach((n) => n.dependencies.forEach((dep) => g.setEdge(dep, n.variable)))
  dagre.layout(g)

  const flowNodes: Node[] = dagNodes.map((n) => {
    const pos = g.node(n.variable)
    const color = getStatusColor(n.status)
    const borderColor = STATUS_NODE_BORDER[color]
    return {
      id: n.variable,
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      data: { dagNode: n },
      style: {
        border: `2px solid ${borderColor}`,
        borderRadius: 6,
        background: '#ffffff',
        padding: '8px 12px',
        width: NODE_W,
        height: NODE_H,
        cursor: 'pointer',
      },
    }
  })

  const edges: Edge[] = []
  dagNodes.forEach((n) =>
    n.dependencies.forEach((dep) => {
      edges.push({
        id: `${dep}->${n.variable}`,
        source: dep,
        target: n.variable,
        animated: n.status === 'in_progress' || n.status === 'verifying',
        style: { stroke: '#64748b', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#64748b', width: 16, height: 16 },
      })
    }),
  )

  return { nodes: flowNodes, edges }
}
