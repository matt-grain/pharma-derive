import { useCallback, useEffect, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Node,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { StatusBadge } from '@/components/StatusBadge'
import { buildLayout } from '@/lib/dag-layout'
import { setCachedPosition } from '@/lib/dag-position-cache'
import { getStatusColor, STATUS_NODE_BORDER } from '@/lib/status'
import type { DAGNode, SourceColumn } from '@/types/api'

type DAGViewProps = {
  workflowId: string
  nodes: DAGNode[]
  onNodeClick?: (node: DAGNode) => void
}

// ---- inner node components ----

function DAGNodeContent({ data }: { data: { dagNode: DAGNode } }) {
  const { dagNode } = data
  return (
    <>
      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden' }} />
      <div className="flex h-full flex-col justify-between">
        <span className="truncate text-xs font-semibold text-slate-800">{dagNode.variable}</span>
        <StatusBadge status={dagNode.status} />
      </div>
      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden' }} />
    </>
  )
}

function SourceColumnNode({ data }: { data: { source: SourceColumn } }) {
  const { source } = data
  return (
    <>
      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden' }} />
      <div className="flex h-full flex-col items-center justify-center gap-1">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
          {source.domain}
        </span>
        <span className="truncate text-xs font-semibold text-slate-700">{source.name}</span>
      </div>
      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden' }} />
    </>
  )
}

// React Flow requires a stable nodeTypes reference — defining it at module scope
// guarantees the same object identity across all renders and component instances.
const NODE_TYPES = { default: DAGNodeContent, sourceColumn: SourceColumnNode }

// ---- main component ----

export function DAGView({ workflowId, nodes: dagNodes, onNodeClick }: DAGViewProps) {
  const { nodes: layoutNodes, edges: layoutEdges } = buildLayout(dagNodes, workflowId)
  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutEdges)

  // Re-layout when dagNodes change (new workflow loaded or status polled).
  // Cached positions are merged inside buildLayout so dragged positions survive.
  useEffect(() => {
    const { nodes: n, edges: e } = buildLayout(dagNodes, workflowId)
    setNodes(n)
    setEdges(e)
  }, [dagNodes, workflowId, setNodes, setEdges])

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
    [setEdges],
  )

  // Persist dragged positions so they survive Radix Tabs unmount/remount.
  function handleNodeDragStop(_: React.MouseEvent, node: Node) {
    setCachedPosition(workflowId, node.id, node.position)
  }

  const [selectedVar, setSelectedVar] = useState<string | null>(null)

  function handleNodeClick(_: React.MouseEvent, node: Node) {
    // Source column nodes carry no DAGNode — ignore clicks on them
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
          onNodeDragStop={handleNodeDragStop}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.2 }}
        >
          <Background color="#e2e8f0" gap={16} />
          <Controls />
          <MiniMap
            nodeColor={(n: Node) => {
              const dag = dagNodes.find((d) => d.variable === n.id)
              return dag
                ? (STATUS_NODE_BORDER[getStatusColor(dag.status)] ?? '#94a3b8')
                : '#94a3b8'
            }}
          />
        </ReactFlow>
      </div>

      {/* Side panel — shown when a derivation node is selected */}
      {selected && (
        <div className="w-72 overflow-auto rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-800">{selected.variable}</h3>
          <div className="mb-3">
            <StatusBadge status={selected.status} />
          </div>
          {selected.qc_verdict && (
            <p className="mb-3 text-xs text-slate-500">
              QC Verdict:{' '}
              <span className="font-medium text-slate-700">{selected.qc_verdict}</span>
            </p>
          )}
          {selected.approved_code && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-600">Approved Code</p>
              <pre className="overflow-auto rounded bg-slate-50 p-2 text-xs font-mono text-slate-700">
                {selected.approved_code}
              </pre>
            </div>
          )}
          {!selected.approved_code && selected.coder_code && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-600">Coder Code</p>
              <pre className="overflow-auto rounded bg-slate-50 p-2 text-xs font-mono text-slate-700">
                {selected.coder_code}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
