import { ArrowLeft, AlertCircle, CheckCircle2, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { StatusBadge } from '@/components/StatusBadge'
import type { WorkflowStatus, WorkflowResult } from '@/types/api'

type WorkflowHeaderProps = {
  status: WorkflowStatus
  workflowId: string
  result: WorkflowResult | undefined
  isApproving: boolean
  onBack: () => void
  onApprove: () => void
}

export function WorkflowHeader({
  status,
  workflowId,
  result,
  isApproving,
  onBack,
  onApprove,
}: WorkflowHeaderProps) {
  return (
    <>
      {/* Breadcrumb */}
      <Button
        variant="ghost"
        size="sm"
        className="mb-5 -ml-2 gap-1.5 text-slate-400 hover:text-slate-700"
        onClick={onBack}
      >
        <ArrowLeft size={14} />
        Dashboard
      </Button>

      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {status.study ?? 'Workflow'}
          </h1>
          <code className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-mono text-slate-500">
            {workflowId.slice(0, 8)}
          </code>
          <StatusBadge status={status.status} />
        </div>

        <div className="mt-2.5 flex items-center gap-5 text-[13px] text-slate-500">
          <span className="flex items-center gap-1.5">
            <Clock size={13} className="text-slate-400" />
            {status.started_at ? new Date(status.started_at).toLocaleString() : 'Not started'}
          </span>
          <span className="inline-block h-3.5 w-px bg-slate-200" />
          <span className="flex items-center gap-1.5">
            <CheckCircle2 size={13} className="text-slate-400" />
            {status.derived_variables.length} variable{status.derived_variables.length !== 1 ? 's' : ''}
          </span>
          {result && (
            <>
              <span className="inline-block h-3.5 w-px bg-slate-200" />
              <span className="flex items-center gap-1.5">
                <Clock size={13} className="text-slate-400" />
                {result.duration_seconds.toFixed(1)}s
              </span>
            </>
          )}
        </div>
      </div>

      {/* Error alert */}
      {status.errors.length > 0 && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {status.errors.map((e, i) => <p key={i}>{e}</p>)}
          </AlertDescription>
        </Alert>
      )}

      {/* HITL approval banner */}
      {status.awaiting_approval && (
        <Alert className="mb-6 border-amber-200 bg-amber-50/80">
          <CheckCircle2 className="h-4 w-4 text-amber-600" />
          <AlertDescription className="flex items-center justify-between">
            <span className="text-[13px] text-amber-800">
              All derivations complete — review the DAG and code, then approve to proceed to audit.
            </span>
            <Button
              size="sm"
              className="ml-4 bg-emerald-600 hover:bg-emerald-700"
              onClick={onApprove}
              disabled={isApproving}
            >
              {isApproving ? 'Approving...' : 'Approve & Run Audit'}
            </Button>
          </AlertDescription>
        </Alert>
      )}
    </>
  )
}
