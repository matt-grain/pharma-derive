import type {
  AuditRecord,
  DAGNode,
  DataPreviewResponse,
  HealthResponse,
  Pipeline,
  SpecItem,
  StartWorkflowResponse,
  WorkflowResult,
  WorkflowStatus,
} from '@/types/api'

const BASE = '/api/v1'

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    // Try to extract a human-friendly reason from the FastAPI error payload
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  healthCheck: (): Promise<HealthResponse> =>
    fetchJson<HealthResponse>('/health'),

  listSpecs: (): Promise<SpecItem[]> =>
    fetchJson<SpecItem[]>(`${BASE}/specs/`),

  getSpecContent: async (filename: string): Promise<string> => {
    const res = await fetch(`${BASE}/specs/${filename}`)
    if (!res.ok) throw new Error(`API error ${res.status}: ${res.statusText}`)
    return res.text()
  },

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

  getWorkflowData: (id: string, limit = 50): Promise<DataPreviewResponse> =>
    fetchJson<DataPreviewResponse>(`${BASE}/workflows/${id}/data?limit=${limit}`),

  downloadAdam: async (id: string, format: 'csv' | 'parquet' = 'csv'): Promise<void> => {
    const res = await fetch(`${BASE}/workflows/${id}/adam?format=${format}`)
    if (!res.ok) throw new Error(`API error ${res.status}: ${res.statusText}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${id}_adam.${format}`
    a.click()
    URL.revokeObjectURL(url)
  },

  getPipeline: (): Promise<Pipeline> =>
    fetchJson<Pipeline>(`${BASE}/pipeline`),

  approveWorkflow: (id: string): Promise<WorkflowStatus> =>
    fetchJson<WorkflowStatus>(`${BASE}/workflows/${id}/approve`, { method: 'POST' }),

  deleteWorkflow: async (id: string): Promise<void> => {
    const res = await fetch(`${BASE}/workflows/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`API error ${res.status}: ${res.statusText}`)
  },

  rerunWorkflow: (id: string): Promise<StartWorkflowResponse> =>
    fetchJson<StartWorkflowResponse>(`${BASE}/workflows/${id}/rerun`, { method: 'POST' }),
}
