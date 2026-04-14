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

const NODE_W = 280
const NODE_H = 96

type StepStyle = { icon: typeof Bot; bg: string; border: string }
// Extracted so the `?? DEFAULT_STEP_STYLE` fallback below is provably non-null
// under noUncheckedIndexedAccess (Record<string, T> index access returns T | undefined).
const DEFAULT_STEP_STYLE: StepStyle = { icon: Cog, bg: '#f8fafc', border: '#cbd5e1' }
const STEP_STYLE: Record<string, StepStyle> = {
  agent:        { icon: Bot,       bg: '#eff6ff', border: '#93c5fd' },
  builtin:      DEFAULT_STEP_STYLE,
  gather:       { icon: GitMerge,  bg: '#f5f3ff', border: '#c4b5fd' },
  parallel_map: { icon: Layers,    bg: '#ecfdf5', border: '#6ee7b7' },
  hitl_gate:    { icon: UserCheck, bg: '#fffbeb', border: '#fcd34d' },
}

/** Build the label showing which agents a step uses. */
function agentLabel(step: PipelineStep): string | null {
  if (step.agent) return step.agent
  if (step.agents && step.agents.length > 0) return step.agents.join(' + ')

  // parallel_map: read agent names from config block
  const coder = step.config['coder_agent']
  const qc = step.config['qc_agent']
  const dbg = step.config['debugger_agent']
  if (coder) {
    const parts = [String(coder)]
    if (qc) parts.push(String(qc))
    if (dbg) parts.push(String(dbg))
    return parts.join(' + ')
  }

  if (step.builtin) return step.builtin
  return null
}

function buildLayout(steps: PipelineStep[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 60 })

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
    const style = STEP_STYLE[s.type] ?? DEFAULT_STEP_STYLE
    return {
      id: s.id,
      type: 'pipeline',
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      data: { step: s },
      style: {
        border: `2px solid ${style.border}`,
        borderRadius: 10,
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
  const style = STEP_STYLE[step.type] ?? DEFAULT_STEP_STYLE
  const Icon = style.icon
  const agents = agentLabel(step)

  return (
    <>
      <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
      <div className="flex h-full flex-col justify-between px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <Icon size={14} className="shrink-0 text-slate-500" />
          <span className="text-[13px] font-semibold text-slate-800">{step.id}</span>
          <span className="ml-auto rounded bg-white/60 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-slate-400">
            {step.type.replace('_', ' ')}
          </span>
        </div>
        <p className="text-[11px] leading-snug text-slate-500">{step.description}</p>
        {agents && (
          <div className="flex items-center gap-1">
            <Bot size={10} className="shrink-0 text-slate-400" />
            <span className="font-mono text-[10px] text-slate-500">{agents}</span>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
    </>
  )
}

export function PipelineView({ steps }: PipelineViewProps) {
  const nodeTypes = useMemo(() => ({ pipeline: PipelineNodeContent }), [])
  const { nodes, edges } = useMemo(() => buildLayout(steps), [steps])

  return (
    <div className="h-[400px] overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
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
