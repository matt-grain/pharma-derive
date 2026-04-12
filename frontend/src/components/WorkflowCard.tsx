import { Clock, CheckCircle2, AlertCircle, Trash2, RotateCw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { StatusBadge } from '@/components/StatusBadge'
import { useRerunWorkflow } from '@/hooks/useWorkflows'
import type { WorkflowStatus } from '@/types/api'

const TERMINAL_STATUSES: readonly string[] = ['completed', 'failed'] as const

type WorkflowCardProps = {
  workflow: WorkflowStatus
  onDelete?: (id: string) => void
}

function formatDuration(started: string | null, completed: string | null, status: string): string {
  if (!started) return '—'
  // Terminal workflows whose completed_at is missing from the DB (pre-patch rows)
  // should show '—', not "now - started" which explodes as time passes.
  if (!completed && TERMINAL_STATUSES.includes(status)) return '—'
  const start = new Date(started).getTime()
  const end = completed ? new Date(completed).getTime() : Date.now()
  const secs = Math.round((end - start) / 1000)
  return secs < 60 ? `${secs}s` : `${Math.round(secs / 60)}m ${secs % 60}s`
}

function formatShortDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

export function WorkflowCard({ workflow, onDelete }: WorkflowCardProps) {
  const navigate = useNavigate()
  const { mutate: rerun, isPending: isRerunning } = useRerunWorkflow()
  const canRerun = workflow.status === 'failed'

  return (
    <Card
      className="cursor-pointer border border-slate-200 transition-shadow hover:shadow-md"
      onClick={() => navigate(`/workflows/${workflow.workflow_id}`)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            {workflow.study && (
              <div className="truncate text-sm font-semibold text-slate-800">{workflow.study}</div>
            )}
            <code className="truncate text-xs text-slate-500">{workflow.workflow_id.slice(0, 12)}</code>
          </div>
          <div className="flex items-center gap-1.5">
            <StatusBadge status={workflow.status} />
            {canRerun && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 text-slate-400 hover:text-blue-500 disabled:opacity-40"
                disabled={isRerunning}
                title="Rerun with the same spec"
                onClick={(e) => { e.stopPropagation(); rerun(workflow.workflow_id) }}
              >
                <RotateCw size={13} className={isRerunning ? 'animate-spin' : ''} />
              </Button>
            )}
            {onDelete && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 text-slate-400 hover:text-red-500"
                onClick={(e) => { e.stopPropagation(); onDelete(workflow.workflow_id) }}
              >
                <Trash2 size={13} />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm">
        <div className="text-xs text-slate-500">
          {!workflow.started_at && !workflow.completed_at ? (
            <span>Not started</span>
          ) : (
            <>
              {formatShortDate(workflow.started_at)}
              {' → '}
              {workflow.completed_at
                ? formatShortDate(workflow.completed_at)
                : TERMINAL_STATUSES.includes(workflow.status)
                  ? '—'
                  : 'running...'}
            </>
          )}
        </div>
        <div className="flex items-center gap-4 text-slate-600">
          <span className="flex items-center gap-1.5">
            <Clock size={12} />
            {formatDuration(workflow.started_at, workflow.completed_at, workflow.status)}
          </span>
          <span className="flex items-center gap-1.5">
            <CheckCircle2 size={12} />
            {workflow.derived_variables.length} vars
          </span>
        </div>
        {workflow.errors.length > 0 && (
          <div className="flex items-center gap-2 text-red-600">
            <AlertCircle size={13} />
            <span>{workflow.errors.length} error(s)</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
