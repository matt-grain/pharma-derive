import { StatusBadge } from '@/components/StatusBadge'
import type { DAGNode } from '@/types/api'

type VariableApprovalListProps = {
  variables: DAGNode[]
  decisions: Record<string, boolean>
  onToggle: (variable: string, approved: boolean) => void
}

export function VariableApprovalList({ variables, decisions, onToggle }: VariableApprovalListProps) {
  return (
    <ul className="max-h-96 overflow-y-auto space-y-2">
      {variables.map((node) => {
        const isApproved = decisions[node.variable] ?? true
        const snippet = node.approved_code?.slice(0, 80) ?? node.coder_code?.slice(0, 80) ?? '—'
        return (
          <li
            key={node.variable}
            className="flex items-start gap-3 rounded-md border border-slate-100 bg-slate-50 p-2.5"
          >
            <input
              type="checkbox"
              id={`approve-${node.variable}`}
              checked={isApproved}
              onChange={(e) => onToggle(node.variable, e.target.checked)}
              className="mt-0.5 h-4 w-4 cursor-pointer accent-emerald-600"
            />
            <label htmlFor={`approve-${node.variable}`} className="flex-1 cursor-pointer space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-800">{node.variable}</span>
                {node.qc_verdict && <StatusBadge status={node.qc_verdict} />}
              </div>
              <code className="block truncate text-xs text-slate-500">{snippet}</code>
            </label>
          </li>
        )
      })}
    </ul>
  )
}
