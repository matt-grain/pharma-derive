import { useCallback, useEffect, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from 'reactflow'
import dagre from '@dagrejs/dagre'
import 'reactflow/dist/style.css'
import { StatusBadge } from '@/components/StatusBadge'
import { getStatusColor, STATUS_NODE_BORDER } from '@/lib/status'
import type { DAGNode } from '@/types/api'

type DAGViewProps = {
  nodes: DAGNode[]
  onNodeClick?: (node: DAGNode) => void
}

const NODE_WIDTH = 180
const NODE_HEIGHT = 64

function buildLayout(dagNodes: DAGNode[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60 })

  dagNodes.forEach((n) => g.setNode(n.variable, { width: NODE_WIDTH, height: NODE_HEIGHT }))

  const edges: Edge[] = []
  dagNodes.forEach((n) => {
    n.dependencies.forEach((dep) => {
      g.setEdge(dep, n.variable)
      edges.push({
        id: `${dep}->${n.variable}`,
        source: dep,
        target: n.variable,
        animated: n.status === 'in_progress' || n.status === 'verifying',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
      })
    })
  })

  dagre.layout(g)

  const flowNodes: Node[] = dagNodes.map((n) => {
    const pos = g.node(n.variable)
    const color = getStatusColor(n.status)
    const borderColor = STATUS_NODE_BORDER[color]
    return {
      id: n.variable,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { dagNode: n },
      style: {
        border: `2px solid ${borderColor}`,
        borderRadius: 6,
        background: '#ffffff',
        padding: '8px 12px',
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        cursor: 'pointer',
      },
    }
  })

  return { nodes: flowNodes, edges }
}

function DAGNodeContent({ data }: { data: { dagNode: DAGNode } }) {
  const { dagNode } = data
  return (
    <div className="flex h-full flex-col justify-between">
      <span className="truncate text-xs font-semibold text-slate-800">{dagNode.variable}</span>
      <StatusBadge status={dagNode.status} />
    </div>
  )
}

const nodeTypes = { default: DAGNodeContent }

export function DAGView({ nodes: dagNodes, onNodeClick }: DAGViewProps) {
  const { nodes: layoutNodes, edges: layoutEdges } = buildLayout(dagNodes)
  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutEdges)

  // Re-layout when dagNodes change
  useEffect(() => {
    const { nodes: n, edges: e } = buildLayout(dagNodes)
    setNodes(n)
    setEdges(e)
  }, [dagNodes, setNodes, setEdges])

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
    [setEdges],
  )

  const [selectedVar, setSelectedVar] = useState<string | null>(null)

  function handleNodeClick(_: React.MouseEvent, node: Node) {
    const dagNode = dagNodes.find((n) => n.variable === node.id)
    if (dagNode) {
      setSelectedVar(node.id === selectedVar ? null : node.id)
      onNodeClick?.(dagNode)
    }
  }

  const selected = selectedVar ? dagNodes.find((n) => n.variable === selectedVar) : null

  return (
    <div className="flex h-[520px] gap-4">
      <div className="flex-1 overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={handleNodeClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
        >
          <Background color="#e2e8f0" gap={16} />
          <Controls />
          <MiniMap nodeColor={(n: Node) => {
            const dag = dagNodes.find((d) => d.variable === n.id)
            return dag ? (STATUS_NODE_BORDER[getStatusColor(dag.status)] ?? '#94a3b8') : '#94a3b8'
          }} />
        </ReactFlow>
      </div>

      {/* Side panel */}
      {selected && (
        <div className="w-72 overflow-auto rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-800">{selected.variable}</h3>
          <div className="mb-3">
            <StatusBadge status={selected.status} />
          </div>
          {selected.qc_verdict && (
            <p className="mb-3 text-xs text-slate-500">
              QC Verdict: <span className="font-medium text-slate-700">{selected.qc_verdict}</span>
            </p>
          )}
          {selected.approved_code && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-600">Approved Code</p>
              <pre className="overflow-auto rounded bg-slate-50 p-2 text-xs text-slate-700 font-mono">
                {selected.approved_code}
              </pre>
            </div>
          )}
          {!selected.approved_code && selected.coder_code && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-600">Coder Code</p>
              <pre className="overflow-auto rounded bg-slate-50 p-2 text-xs text-slate-700 font-mono">
                {selected.coder_code}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
