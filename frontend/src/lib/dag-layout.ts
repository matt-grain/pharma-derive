// DAG layout helpers — pure layout logic, no React.
// Separated from DAGView.tsx to keep that file under 200 lines.
import dagre from '@dagrejs/dagre'
import { MarkerType, type Edge, type Node } from 'reactflow'
import { getStatusColor, STATUS_NODE_BORDER } from '@/lib/status'
import { getCachedPosition } from '@/lib/dag-position-cache'
import { buildDerivationOnlyLayout } from '@/lib/dag-layout-fallback'
import type { DAGNode, SourceColumn } from '@/types/api'

export const DERIV_NODE_WIDTH = 180
export const DERIV_NODE_HEIGHT = 64
const SRC_NODE_WIDTH = 120
const SRC_NODE_HEIGHT = 50

// Stable key for a source column across the whole graph.
export type SourceKey = `${string}:${string}`

export function sourceKey(sc: SourceColumn): SourceKey {
  return `${sc.domain}:${sc.name}`
}

// React-Flow node id for a source column.
export function srcNodeId(sc: SourceColumn): string {
  return `src:${sc.domain}:${sc.name}`
}

/** Collect all unique source columns referenced across the derivation set. */
function collectSources(dagNodes: DAGNode[]): Map<SourceKey, SourceColumn> {
  const sources = new Map<SourceKey, SourceColumn>()
  for (const node of dagNodes) {
    for (const sc of node.source_columns ?? []) {
      sources.set(sourceKey(sc), sc)
    }
  }
  return sources
}

/**
 * Unified dagre layout — all source columns + derivation nodes in a single
 * dagre pass. Dagre's barycentric crossing-minimisation naturally positions
 * each source node near its consumers, eliminating the manual row that
 * produced crossing edges.
 */
function buildUnifiedLayout(
  dagNodes: DAGNode[],
  workflowId: string,
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 30, ranksep: 70, ranker: 'tight-tree' })

  const sources = collectSources(dagNodes)

  // Source column nodes — no predecessors, dagre places them at rank 0.
  for (const [key] of sources.entries()) {
    g.setNode(`src:${key}`, { width: SRC_NODE_WIDTH, height: SRC_NODE_HEIGHT })
  }

  // Derivation nodes
  for (const n of dagNodes) {
    g.setNode(n.variable, { width: DERIV_NODE_WIDTH, height: DERIV_NODE_HEIGHT })
  }

  // Source → derivation edges (crossing-minimisation input)
  for (const n of dagNodes) {
    for (const sc of n.source_columns ?? []) {
      g.setEdge(`src:${sourceKey(sc)}`, n.variable)
    }
  }

  // Derivation → derivation edges
  for (const n of dagNodes) {
    for (const dep of n.dependencies) {
      g.setEdge(dep, n.variable)
    }
  }

  dagre.layout(g)

  const flowNodes: Node[] = []
  const flowEdges: Edge[] = []

  // Build source column flow nodes
  for (const [key, sc] of sources.entries()) {
    const pos = g.node(`src:${key}`)
    const nodeId = `src:${key}`
    const cached = getCachedPosition(workflowId, nodeId)
    flowNodes.push({
      id: nodeId,
      type: 'sourceColumn',
      position: cached ?? { x: pos.x - SRC_NODE_WIDTH / 2, y: pos.y - SRC_NODE_HEIGHT / 2 },
      data: { source: sc },
      style: {
        width: SRC_NODE_WIDTH,
        height: SRC_NODE_HEIGHT,
        background: '#f8fafc',
        border: '1px dashed #94a3b8',
        borderRadius: 4,
        padding: '6px 8px',
        cursor: 'default',
      },
    })
  }

  // Build derivation flow nodes
  for (const n of dagNodes) {
    const pos = g.node(n.variable)
    const color = getStatusColor(n.status)
    const borderColor = STATUS_NODE_BORDER[color]
    const cached = getCachedPosition(workflowId, n.variable)
    flowNodes.push({
      id: n.variable,
      position: cached ?? { x: pos.x - DERIV_NODE_WIDTH / 2, y: pos.y - DERIV_NODE_HEIGHT / 2 },
      data: { dagNode: n },
      style: {
        border: `2px solid ${borderColor}`,
        borderRadius: 6,
        background: '#ffffff',
        padding: '8px 12px',
        width: DERIV_NODE_WIDTH,
        height: DERIV_NODE_HEIGHT,
        cursor: 'pointer',
      },
    })
  }

  // Source → derivation edges (dashed, slate)
  for (const n of dagNodes) {
    for (const sc of n.source_columns ?? []) {
      flowEdges.push({
        id: `src:${sourceKey(sc)}->${n.variable}`,
        source: `src:${sourceKey(sc)}`,
        target: n.variable,
        style: { stroke: '#94a3b8', strokeWidth: 1.5, strokeDasharray: '4 3' },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8', width: 14, height: 14 },
      })
    }
  }

  // Derivation → derivation edges (solid, animated when active)
  for (const n of dagNodes) {
    for (const dep of n.dependencies) {
      flowEdges.push({
        id: `${dep}->${n.variable}`,
        source: dep,
        target: n.variable,
        animated: n.status === 'in_progress' || n.status === 'verifying',
        style: { stroke: '#64748b', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#64748b', width: 16, height: 16 },
      })
    }
  }

  return { nodes: flowNodes, edges: flowEdges }
}

/**
 * Full layout builder.
 *
 * When no node carries source_columns (old workflows), falls back to
 * derivation-only layout — identical output to the pre-lineage code.
 * Otherwise, runs a unified dagre pass over all nodes to minimise crossings.
 */
export function buildLayout(
  dagNodes: DAGNode[],
  workflowId: string,
): { nodes: Node[]; edges: Edge[] } {
  const hasSourceInfo = dagNodes.some((n) => (n.source_columns ?? []).length > 0)

  if (!hasSourceInfo) {
    return buildDerivationOnlyLayout(dagNodes)
  }

  return buildUnifiedLayout(dagNodes, workflowId)
}
