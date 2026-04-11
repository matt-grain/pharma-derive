import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, AlertCircle, CheckCircle2, Clock, BarChart3, GitBranch, Code2, Shield, Database, Workflow } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { StatusBadge } from '@/components/StatusBadge'
import { StatusTab } from '@/components/StatusTab'
import { DAGView } from '@/components/DAGView'
import { CodePanel } from '@/components/CodePanel'
import { AuditTable } from '@/components/AuditTable'
import { DataTab } from '@/components/DataTab'
import { PipelineView } from '@/components/PipelineView'
import { useWorkflowStatus, useWorkflowDag, useWorkflowAudit, useWorkflowResult, useWorkflowData, useApproveWorkflow, usePipeline } from '@/hooks/useWorkflows'
import { TERMINAL_STATUSES } from '@/lib/status'

export function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const workflowId = id ?? ''

  const { data: status, isLoading, error } = useWorkflowStatus(workflowId)
  const { data: dagNodes } = useWorkflowDag(workflowId)
  const { data: auditRecords } = useWorkflowAudit(workflowId)
  const isTerminal = (TERMINAL_STATUSES as readonly string[]).includes(status?.status ?? '')
  const { data: result } = useWorkflowResult(workflowId, isTerminal)
  const { data: dataPreview, isLoading: isDataLoading } = useWorkflowData(workflowId, isTerminal)
  const { mutate: approve, isPending: isApproving } = useApproveWorkflow(workflowId)
  const { data: pipeline } = usePipeline()

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
      {/* Breadcrumb */}
      <Button
        variant="ghost"
        size="sm"
        className="mb-5 -ml-2 gap-1.5 text-slate-400 hover:text-slate-700"
        onClick={() => navigate('/')}
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
              onClick={() => approve()}
              disabled={isApproving}
            >
              {isApproving ? 'Approving...' : 'Approve & Run Audit'}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs defaultValue="status">
        <TabsList className="mb-6 flex w-full gap-1 rounded-xl bg-slate-100/80 p-1.5">
          <TabsTrigger value="status" className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-500 transition-all data-[selected]:bg-white data-[selected]:text-slate-900 data-[selected]:shadow-sm">
            <BarChart3 size={15} />
            Status
          </TabsTrigger>
          <TabsTrigger value="dag" className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-500 transition-all data-[selected]:bg-white data-[selected]:text-slate-900 data-[selected]:shadow-sm">
            <GitBranch size={15} />
            DAG
          </TabsTrigger>
          <TabsTrigger value="code" className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-500 transition-all data-[selected]:bg-white data-[selected]:text-slate-900 data-[selected]:shadow-sm">
            <Code2 size={15} />
            Code
          </TabsTrigger>
          <TabsTrigger value="audit" className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-500 transition-all data-[selected]:bg-white data-[selected]:text-slate-900 data-[selected]:shadow-sm">
            <Shield size={15} />
            Audit
            {auditRecords && auditRecords.length > 0 && (
              <span className="ml-0.5 rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-600">
                {auditRecords.length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="data" className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-500 transition-all data-[selected]:bg-white data-[selected]:text-slate-900 data-[selected]:shadow-sm">
            <Database size={15} />
            Data
          </TabsTrigger>
          <TabsTrigger value="pipeline" className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-500 transition-all data-[selected]:bg-white data-[selected]:text-slate-900 data-[selected]:shadow-sm">
            <Workflow size={15} />
            Pipeline
          </TabsTrigger>
        </TabsList>

        <TabsContent value="status">
          <StatusTab status={status} result={result} />
        </TabsContent>

        <TabsContent value="dag">
          {dagNodes && dagNodes.length > 0 ? (
            <DAGView nodes={dagNodes} />
          ) : (
            <div className="rounded-xl border border-dashed border-slate-200 py-20 text-center text-sm text-slate-400">
              DAG not yet available
            </div>
          )}
        </TabsContent>

        <TabsContent value="code">
          <div className="space-y-4">
            {dagNodes && dagNodes.length > 0 ? (
              dagNodes.map((node) => <CodePanel key={node.variable} node={node} />)
            ) : (
              <div className="rounded-xl border border-dashed border-slate-200 py-20 text-center text-sm text-slate-400">
                No code generated yet
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="audit">
          <AuditTable records={auditRecords ?? []} />
        </TabsContent>

        <TabsContent value="data">
          <DataTab
            workflowId={workflowId}
            data={dataPreview}
            isLoading={isDataLoading}
          />
        </TabsContent>

        <TabsContent value="pipeline">
          {pipeline ? (
            <PipelineView steps={pipeline.steps} />
          ) : (
            <div className="rounded-xl border border-dashed border-slate-200 py-20 text-center text-sm text-slate-400">
              Pipeline definition not available
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
