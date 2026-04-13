import { BarChart3, GitBranch, Code2, Shield, Database, Workflow } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { StatusTab } from '@/components/StatusTab'
import { DAGView } from '@/components/DAGView'
import { CodePanel } from '@/components/CodePanel'
import { AuditTable } from '@/components/AuditTable'
import { DataTab } from '@/components/DataTab'
import { PipelineView } from '@/components/PipelineView'
import type { WorkflowStatus, WorkflowResult, DAGNode, AuditRecord, DataPreviewResponse, Pipeline } from '@/types/api'

type WorkflowTabsProps = {
  status: WorkflowStatus
  result: WorkflowResult | undefined
  dagNodes: DAGNode[] | undefined
  auditRecords: AuditRecord[] | undefined
  workflowId: string
  dataPreview: DataPreviewResponse | undefined
  isDataLoading: boolean
  pipeline: Pipeline | undefined
}

const TAB_TRIGGER_CLASS =
  'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-500 transition-all data-[selected]:bg-white data-[selected]:text-slate-900 data-[selected]:shadow-sm'

const EMPTY_STATE_CLASS =
  'rounded-xl border border-dashed border-slate-200 py-20 text-center text-sm text-slate-400'

export function WorkflowTabs({
  status,
  result,
  dagNodes,
  auditRecords,
  workflowId,
  dataPreview,
  isDataLoading,
  pipeline,
}: WorkflowTabsProps) {
  return (
    <Tabs defaultValue="status">
      <TabsList className="mb-6 flex w-full gap-1 rounded-xl bg-slate-100/80 p-1.5">
        <TabsTrigger value="status" className={TAB_TRIGGER_CLASS}>
          <BarChart3 size={15} />
          Status
        </TabsTrigger>
        <TabsTrigger value="dag" className={TAB_TRIGGER_CLASS}>
          <GitBranch size={15} />
          DAG
        </TabsTrigger>
        <TabsTrigger value="code" className={TAB_TRIGGER_CLASS}>
          <Code2 size={15} />
          Code
        </TabsTrigger>
        <TabsTrigger value="audit" className={TAB_TRIGGER_CLASS}>
          <Shield size={15} />
          Audit
          {auditRecords && auditRecords.length > 0 && (
            <span className="ml-0.5 rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-600">
              {auditRecords.length}
            </span>
          )}
        </TabsTrigger>
        <TabsTrigger value="data" className={TAB_TRIGGER_CLASS}>
          <Database size={15} />
          Data
        </TabsTrigger>
        <TabsTrigger value="pipeline" className={TAB_TRIGGER_CLASS}>
          <Workflow size={15} />
          Pipeline
        </TabsTrigger>
      </TabsList>

      <TabsContent value="status">
        <StatusTab status={status} result={result} />
      </TabsContent>

      <TabsContent value="dag">
        {dagNodes && dagNodes.length > 0 ? (
          <DAGView workflowId={workflowId} nodes={dagNodes} />
        ) : (
          <div className={EMPTY_STATE_CLASS}>DAG not yet available</div>
        )}
      </TabsContent>

      <TabsContent value="code">
        <div className="space-y-4">
          {dagNodes && dagNodes.length > 0 ? (
            dagNodes.map((node) => (
              <CodePanel
                key={node.variable}
                node={node}
                workflowId={workflowId}
                status={status}
              />
            ))
          ) : (
            <div className={EMPTY_STATE_CLASS}>No code generated yet</div>
          )}
        </div>
      </TabsContent>

      <TabsContent value="audit">
        <AuditTable records={auditRecords ?? []} />
      </TabsContent>

      <TabsContent value="data">
        <DataTab workflowId={workflowId} data={dataPreview} isLoading={isDataLoading} />
      </TabsContent>

      <TabsContent value="pipeline">
        {pipeline ? (
          <PipelineView steps={pipeline.steps} />
        ) : (
          <div className={EMPTY_STATE_CLASS}>Pipeline definition not available</div>
        )}
      </TabsContent>
    </Tabs>
  )
}
