import type { DAGNode } from '@/types/api'
import { StatusBadge } from '@/components/StatusBadge'

type CodePanelProps = {
  node: DAGNode
}

function CodeBlock({ title, code }: { title: string; code: string | null }) {
  if (!code) return null
  return (
    <div className="flex-1 min-w-0">
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <pre
        className="overflow-auto rounded-md border border-slate-200 bg-slate-950 p-4 text-xs leading-relaxed text-emerald-300"
        style={{ fontFamily: "'JetBrains Mono', monospace", maxHeight: 320 }}
      >
        {code}
      </pre>
    </div>
  )
}

function resolveLabel(node: DAGNode): string {
  if (node.qc_verdict === 'match') {
    return 'QC: match — coder version approved'
  }
  if (node.qc_verdict !== 'mismatch') return ''
  if (node.status !== 'approved') return 'QC: mismatch — unresolved'
  // Mismatch resolved by debugger — which version was approved?
  if (node.approved_code === node.qc_code) return 'QC: mismatch — resolved by debugger, QC version approved'
  if (node.approved_code === node.coder_code) return 'QC: mismatch — resolved by debugger, coder version approved'
  return 'QC: mismatch — resolved by debugger, fix applied'
}

export function CodePanel({ node }: CodePanelProps) {
  const hasCode = node.coder_code ?? node.qc_code ?? node.approved_code

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-sm font-semibold text-slate-800">{node.variable}</h3>
        <StatusBadge status={node.status} />
        <span className="text-xs text-slate-500">{resolveLabel(node)}</span>
      </div>

      {!hasCode && (
        <p className="text-xs text-slate-400">No code generated yet</p>
      )}

      <div className="flex gap-4">
        <CodeBlock title="Coder" code={node.coder_code} />
        <CodeBlock title="QC" code={node.qc_code} />
        {node.approved_code && node.approved_code !== node.coder_code && (
          <CodeBlock title="Approved" code={node.approved_code} />
        )}
      </div>
    </div>
  )
}
