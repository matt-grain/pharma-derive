import { Clock, CheckCircle2, AlertCircle, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { StatusBadge } from '@/components/StatusBadge'
import type { WorkflowStatus } from '@/types/api'

type WorkflowCardProps = {
  workflow: WorkflowStatus
  onDelete?: (id: string) => void
}

function formatDuration(started: string | null, completed: string | null): string {
  if (!started) return '—'
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
          {formatShortDate(workflow.started_at)}
          {workflow.completed_at ? ` → ${formatShortDate(workflow.completed_at)}` : ' → running...'}
        </div>
        <div className="flex items-center gap-4 text-slate-600">
          <span className="flex items-center gap-1.5">
            <Clock size={12} />
            {formatDuration(workflow.started_at, workflow.completed_at)}
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
