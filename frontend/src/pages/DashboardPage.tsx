import { useState } from 'react'
import { Plus, Activity } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { WorkflowCard } from '@/components/WorkflowCard'
import { NewWorkflowDialog } from '@/components/NewWorkflowDialog'
import { useWorkflows } from '@/hooks/useWorkflows'

export function DashboardPage() {
  const { data: workflows, isLoading, error } = useWorkflows()
  const [dialogOpen, setDialogOpen] = useState(false)

  const active = workflows?.filter((w) => !['completed', 'failed'].includes(w.status)) ?? []
  const completed = workflows?.filter((w) => ['completed', 'failed'].includes(w.status)) ?? []

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Workflow Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Clinical data derivation runs — SDTM to ADaM
          </p>
        </div>
        <Button
          onClick={() => setDialogOpen(true)}
          className="flex items-center gap-2"
          style={{ backgroundColor: '#0f172a' }}
        >
          <Plus size={15} />
          New Workflow
        </Button>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-36 animate-pulse rounded-lg bg-slate-200" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Failed to load workflows. Ensure the backend is running on port 8000.
        </div>
      )}

      {/* Active workflows */}
      {active.length > 0 && (
        <section className="mb-8">
          <div className="mb-3 flex items-center gap-2">
            <Activity size={14} className="text-amber-500" />
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
              Active ({active.length})
            </h2>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {active.map((w) => (
              <WorkflowCard key={w.workflow_id} workflow={w} />
            ))}
          </div>
        </section>
      )}

      {/* Completed workflows */}
      {completed.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Completed ({completed.length})
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {completed.map((w) => (
              <WorkflowCard key={w.workflow_id} workflow={w} />
            ))}
          </div>
        </section>
      )}

      {!isLoading && !error && workflows?.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 py-20 text-center">
          <p className="text-slate-500">No workflows yet.</p>
          <p className="mt-1 text-sm text-slate-400">Click "New Workflow" to run your first derivation.</p>
        </div>
      )}

      <NewWorkflowDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  )
}
