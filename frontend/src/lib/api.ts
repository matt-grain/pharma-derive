import type {
  AuditRecord,
  DAGNode,
  HealthResponse,
  SpecItem,
  StartWorkflowResponse,
  WorkflowResult,
  WorkflowStatus,
} from '@/types/api'

const BASE = '/api/v1'

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  healthCheck: (): Promise<HealthResponse> =>
    fetchJson<HealthResponse>('/health'),

  listSpecs: (): Promise<SpecItem[]> =>
    fetchJson<SpecItem[]>(`${BASE}/specs/`),

  startWorkflow: (specPath: string): Promise<StartWorkflowResponse> =>
    fetchJson<StartWorkflowResponse>(`${BASE}/workflows/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec_path: specPath }),
    }),

  listWorkflows: (): Promise<WorkflowStatus[]> =>
    fetchJson<WorkflowStatus[]>(`${BASE}/workflows/`),

  getWorkflowStatus: (id: string): Promise<WorkflowStatus> =>
    fetchJson<WorkflowStatus>(`${BASE}/workflows/${id}`),

  getWorkflowResult: (id: string): Promise<WorkflowResult> =>
    fetchJson<WorkflowResult>(`${BASE}/workflows/${id}/result`),

  getWorkflowAudit: (id: string): Promise<AuditRecord[]> =>
    fetchJson<AuditRecord[]>(`${BASE}/workflows/${id}/audit`),

  getWorkflowDag: (id: string): Promise<DAGNode[]> =>
    fetchJson<DAGNode[]>(`${BASE}/workflows/${id}/dag`),

  approveWorkflow: (id: string): Promise<WorkflowStatus> =>
    fetchJson<WorkflowStatus>(`${BASE}/workflows/${id}/approve`, { method: 'POST' }),

  deleteWorkflow: async (id: string): Promise<void> => {
    const res = await fetch(`${BASE}/workflows/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`API error ${res.status}: ${res.statusText}`)
  },
}
