import { useParams, useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { WorkflowHeader } from '@/components/WorkflowHeader'
import { WorkflowTabs } from '@/components/WorkflowTabs'
import {
  useWorkflowStatus,
  useWorkflowDag,
  useWorkflowAudit,
  useWorkflowResult,
  useWorkflowData,
  useApproveWorkflowWithFeedback,
  useRejectWorkflow,
  usePipeline,
} from '@/hooks/useWorkflows'
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
  const approveMutation = useApproveWorkflowWithFeedback(workflowId)
  const rejectMutation = useRejectWorkflow(workflowId)
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
      <WorkflowHeader
        status={status}
        workflowId={workflowId}
        result={result}
        dagNodes={dagNodes ?? []}
        isApproving={approveMutation.isPending}
        isRejecting={rejectMutation.isPending}
        onBack={() => navigate('/')}
        onApproveWithFeedback={(payload) => approveMutation.mutate(payload)}
        onReject={(reason) => rejectMutation.mutate({ reason })}
      />
      <WorkflowTabs
        status={status}
        result={result}
        dagNodes={dagNodes}
        auditRecords={auditRecords}
        workflowId={workflowId}
        dataPreview={dataPreview}
        isDataLoading={isDataLoading}
        pipeline={pipeline}
      />
    </div>
  )
}
