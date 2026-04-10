import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, AlertCircle, CheckCircle2, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { StatusBadge } from '@/components/StatusBadge'
import { StatusTab } from '@/components/StatusTab'
import { DAGView } from '@/components/DAGView'
import { CodePanel } from '@/components/CodePanel'
import { AuditTable } from '@/components/AuditTable'
import { useWorkflowStatus, useWorkflowDag, useWorkflowAudit, useWorkflowResult } from '@/hooks/useWorkflows'

const TERMINAL = ['completed', 'failed']

export function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const workflowId = id ?? ''

  const { data: status, isLoading, error } = useWorkflowStatus(workflowId)
  const { data: dagNodes } = useWorkflowDag(workflowId)
  const { data: auditRecords } = useWorkflowAudit(workflowId)
  const isTerminal = TERMINAL.includes(status?.status ?? '')
  const { data: result } = useWorkflowResult(workflowId, isTerminal)

  if (isLoading) {
    return (
      <div className="p-8 space-y-4">
        <div className="h-8 w-64 animate-pulse rounded bg-slate-200" />
        <div className="h-48 animate-pulse rounded-lg bg-slate-200" />
      </div>
    )
  }

  if (error ?? !status) {
    return (
      <div className="p-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>Workflow not found or backend unreachable.</AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="p-8">
      <Button
        variant="ghost"
        size="sm"
        className="mb-4 gap-1.5 text-slate-500 hover:text-slate-800"
        onClick={() => navigate('/')}
      >
        <ArrowLeft size={14} />
        Dashboard
      </Button>

      <div className="mb-2 flex items-center gap-4">
        <h1 className="text-xl font-semibold text-slate-900">
          Workflow{' '}
          <code className="rounded bg-slate-100 px-2 py-0.5 text-base">
            {workflowId.slice(0, 16)}…
          </code>
        </h1>
        <StatusBadge status={status.status} />
      </div>

      <div className="mb-6 flex gap-6 text-sm text-slate-600">
        <span className="flex items-center gap-1.5">
          <Clock size={13} />
          {status.started_at ? new Date(status.started_at).toLocaleString() : 'Not started'}
        </span>
        <span className="flex items-center gap-1.5">
          <CheckCircle2 size={13} />
          {status.derived_variables.length} variables
        </span>
        {result && (
          <span className="flex items-center gap-1.5">
            <Clock size={13} />
            {result.duration_seconds.toFixed(1)}s total
          </span>
        )}
      </div>

      {status.errors.length > 0 && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {status.errors.map((e, i) => <p key={i}>{e}</p>)}
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="status">
        <TabsList className="mb-4">
          <TabsTrigger value="status">Status</TabsTrigger>
          <TabsTrigger value="dag">DAG</TabsTrigger>
          <TabsTrigger value="code">Code</TabsTrigger>
          <TabsTrigger value="audit">Audit</TabsTrigger>
        </TabsList>

        <TabsContent value="status">
          <StatusTab status={status} result={result} />
        </TabsContent>

        <TabsContent value="dag">
          {dagNodes && dagNodes.length > 0 ? (
            <DAGView nodes={dagNodes} />
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 py-16 text-center text-slate-400">
              DAG not yet available
            </div>
          )}
        </TabsContent>

        <TabsContent value="code">
          <div className="space-y-4">
            {dagNodes && dagNodes.length > 0 ? (
              dagNodes.map((node) => <CodePanel key={node.variable} node={node} />)
            ) : (
              <div className="rounded-lg border border-dashed border-slate-300 py-16 text-center text-slate-400">
                No code generated yet
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="audit">
          <AuditTable records={auditRecords ?? []} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
