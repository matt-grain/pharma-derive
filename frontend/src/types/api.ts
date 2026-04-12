export interface WorkflowStatus {
  workflow_id: string
  status: string
  study: string | null
  awaiting_approval: boolean
  started_at: string | null
  completed_at: string | null
  derived_variables: string[]
  errors: string[]
}

export interface WorkflowResult {
  workflow_id: string
  study: string
  status: string
  derived_variables: string[]
  qc_summary: Record<string, string>
  audit_summary: Record<string, unknown> | null
  errors: string[]
  duration_seconds: number
}

export interface AuditRecord {
  timestamp: string
  workflow_id: string
  variable: string
  action: string
  agent: string
  details: Record<string, string | number | boolean | null>
}

export interface SourceColumn {
  name: string    // e.g. "AGE", "RFXSTDTC"
  domain: string  // e.g. "dm", "ex", "ds", "sv" (lowercase CDISC domain code)
}

export interface DAGNode {
  variable: string
  status: string
  layer: number
  coder_code: string | null
  qc_code: string | null
  qc_verdict: string | null
  approved_code: string | null
  dependencies: string[]
  source_columns: SourceColumn[]  // SDTM columns this derivation reads; empty array for old workflows
}

export interface SpecItem {
  filename: string
  study: string
  description: string
  derivation_count: number
}

export interface HealthResponse {
  status: string
  version: string
  workflows_in_progress: number
}

export interface StartWorkflowResponse {
  workflow_id: string
  status: string
  message: string
}

export interface ColumnInfo {
  name: string
  dtype: string
  null_count: number
  sample_values: (string | number | null)[]
}

export interface DatasetPreview {
  label: string
  row_count: number
  column_count: number
  columns: ColumnInfo[]
  rows: Record<string, string | number | null>[]
}

export interface DataPreviewResponse {
  workflow_id: string
  source: DatasetPreview | null
  derived: DatasetPreview | null
  derived_formats: string[]
}

export interface PipelineStep {
  id: string
  type: string
  description: string
  agent: string | null
  agents: string[] | null
  builtin: string | null
  depends_on: string[]
  config: Record<string, string | number | boolean | string[]>
  has_sub_steps: boolean
}

export interface Pipeline {
  name: string
  version: string
  description: string
  steps: PipelineStep[]
}
