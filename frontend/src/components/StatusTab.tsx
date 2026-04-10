import { StatusBadge } from '@/components/StatusBadge'
import type { WorkflowResult, WorkflowStatus } from '@/types/api'

type StatusTabProps = {
  status: WorkflowStatus
  result: WorkflowResult | undefined
}

export function StatusTab({ status, result }: StatusTabProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-700">Derived Variables</h3>
        {status.derived_variables.length === 0 ? (
          <p className="text-sm text-slate-400">None yet</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {status.derived_variables.map((v) => (
              <code key={v} className="rounded bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                {v}
              </code>
            ))}
          </div>
        )}
      </div>
      {result?.qc_summary && Object.keys(result.qc_summary).length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">QC Summary</h3>
          <div className="space-y-1.5">
            {Object.entries(result.qc_summary).map(([k, v]) => (
              <div key={k} className="flex justify-between text-sm">
                <span className="text-slate-600">{k}</span>
                <StatusBadge status={v} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
