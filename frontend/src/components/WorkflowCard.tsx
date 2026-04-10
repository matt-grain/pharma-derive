import { Clock, CheckCircle2, AlertCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { StatusBadge } from '@/components/StatusBadge'
import type { WorkflowStatus } from '@/types/api'

type WorkflowCardProps = {
  workflow: WorkflowStatus
}

function formatDuration(started: string | null, completed: string | null): string {
  if (!started) return '—'
  const start = new Date(started).getTime()
  const end = completed ? new Date(completed).getTime() : Date.now()
  const secs = Math.round((end - start) / 1000)
  return secs < 60 ? `${secs}s` : `${Math.round(secs / 60)}m ${secs % 60}s`
}

export function WorkflowCard({ workflow }: WorkflowCardProps) {
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
          <StatusBadge status={workflow.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex items-center gap-2 text-slate-600">
          <Clock size={13} />
          <span>{formatDuration(workflow.started_at, workflow.completed_at)}</span>
        </div>
        <div className="flex items-center gap-2 text-slate-600">
          <CheckCircle2 size={13} />
          <span>{workflow.derived_variables.length} variables derived</span>
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
