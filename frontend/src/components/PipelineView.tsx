import { useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  type Edge,
  type Node,
} from 'reactflow'
import dagre from '@dagrejs/dagre'
import 'reactflow/dist/style.css'
import { Bot, Cog, GitMerge, Layers, UserCheck } from 'lucide-react'
import type { PipelineStep } from '@/types/api'

type PipelineViewProps = {
  steps: PipelineStep[]
}

const NODE_W = 220
const NODE_H = 80

const STEP_STYLE: Record<string, { icon: typeof Bot; bg: string; border: string }> = {
  agent:        { icon: Bot,       bg: '#eff6ff', border: '#93c5fd' },
  builtin:      { icon: Cog,       bg: '#f8fafc', border: '#cbd5e1' },
  gather:       { icon: GitMerge,  bg: '#f5f3ff', border: '#c4b5fd' },
  parallel_map: { icon: Layers,    bg: '#ecfdf5', border: '#6ee7b7' },
  hitl_gate:    { icon: UserCheck, bg: '#fffbeb', border: '#fcd34d' },
}

function buildLayout(steps: PipelineStep[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 30, ranksep: 80 })

  steps.forEach((s) => g.setNode(s.id, { width: NODE_W, height: NODE_H }))

  const edges: Edge[] = []
  steps.forEach((s) => {
    s.depends_on.forEach((dep) => {
      g.setEdge(dep, s.id)
      edges.push({
        id: `${dep}->${s.id}`,
        source: dep,
        target: s.id,
        animated: true,
        style: { stroke: '#94a3b8', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8', width: 14, height: 14 },
      })
    })
  })

  dagre.layout(g)

  const flowNodes: Node[] = steps.map((s) => {
    const pos = g.node(s.id)
    const style = STEP_STYLE[s.type] ?? STEP_STYLE['builtin']
    return {
      id: s.id,
      type: 'pipeline',
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      data: { step: s },
      style: {
        border: `2px solid ${style.border}`,
        borderRadius: 8,
        background: style.bg,
        width: NODE_W,
        height: NODE_H,
        padding: 0,
      },
    }
  })

  return { nodes: flowNodes, edges }
}

function PipelineNodeContent({ data }: { data: { step: PipelineStep } }) {
  const { step } = data
  const style = STEP_STYLE[step.type] ?? STEP_STYLE['builtin']
  const Icon = style.icon
  const label = step.agent ?? step.agents?.join(' + ') ?? step.builtin ?? step.type

  return (
    <>
      <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
      <div className="flex h-full flex-col justify-between px-3 py-2">
        <div className="flex items-center gap-1.5">
          <Icon size={13} className="shrink-0 text-slate-500" />
          <span className="truncate text-xs font-semibold text-slate-800">{step.id}</span>
        </div>
        {step.description && (
          <p className="truncate text-[10px] text-slate-500">{step.description}</p>
        )}
        <span className="truncate font-mono text-[10px] text-slate-400">{label}</span>
      </div>
      <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
    </>
  )
}

export function PipelineView({ steps }: PipelineViewProps) {
  const nodeTypes = useMemo(() => ({ pipeline: PipelineNodeContent }), [])
  const { nodes, edges } = useMemo(() => buildLayout(steps), [steps])

  return (
    <div className="h-[340px] overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e2e8f0" gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
