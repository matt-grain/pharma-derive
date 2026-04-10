export interface WorkflowStatus {
  workflow_id: string
  status: string
  study: string | null
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

export interface DAGNode {
  variable: string
  status: string
  layer: number
  coder_code: string | null
  qc_code: string | null
  qc_verdict: string | null
  approved_code: string | null
  dependencies: string[]
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
