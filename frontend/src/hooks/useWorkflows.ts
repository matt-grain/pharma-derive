import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { TERMINAL_STATUSES } from '@/lib/status'
import type { ApprovalRequest, RejectionRequest, VariableOverrideRequest } from '@/types/api'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.healthCheck,
    refetchInterval: 30_000,
  })
}

export function useSpecs() {
  return useQuery({
    queryKey: ['specs'],
    queryFn: api.listSpecs,
  })
}

export function useWorkflows() {
  return useQuery({
    queryKey: ['workflows'],
    queryFn: api.listWorkflows,
    refetchInterval: 3_000,
  })
}

export function useWorkflowStatus(id: string) {
  return useQuery({
    queryKey: ['workflow', id],
    queryFn: () => api.getWorkflowStatus(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status !== undefined && (TERMINAL_STATUSES as readonly string[]).includes(status)
        ? false
        : 2_000
    },
  })
}

export function useWorkflowResult(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ['workflow', id, 'result'],
    queryFn: () => api.getWorkflowResult(id),
    enabled,
    retry: false,
  })
}

export function useWorkflowAudit(id: string) {
  return useQuery({
    queryKey: ['workflow', id, 'audit'],
    queryFn: () => api.getWorkflowAudit(id),
    enabled: id.length > 0,
  })
}

export function useWorkflowDag(id: string) {
  return useQuery({
    queryKey: ['workflow', id, 'dag'],
    queryFn: () => api.getWorkflowDag(id),
    enabled: id.length > 0,
  })
}

export function useWorkflowData(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ['workflow', id, 'data'],
    queryFn: () => api.getWorkflowData(id),
    enabled,
    staleTime: 60_000, // Data preview is static once workflow completes — cache 1 min
  })
}

export function usePipeline() {
  return useQuery({
    queryKey: ['pipeline'],
    queryFn: api.getPipeline,
    staleTime: 300_000, // Pipeline config rarely changes — cache 5 min
  })
}

export function useStartWorkflow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (specPath: string) => api.startWorkflow(specPath),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })
}

export function useApproveWorkflow(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.approveWorkflow(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflow', id] })
    },
  })
}

export function useDeleteWorkflow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteWorkflow(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })
}

export function useRerunWorkflow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.rerunWorkflow(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
     
    onError: (err: Error) => { alert(`Cannot rerun this workflow\n\n${err.message}`) },
  })
}

export function useApproveWorkflowWithFeedback(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ApprovalRequest) => api.approveWorkflowWithFeedback(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflow', id] })
      void queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })
}

export function useRejectWorkflow(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: RejectionRequest) => api.rejectWorkflow(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflow', id] })
      void queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })
}

export function useOverrideVariable(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ variable, payload }: { variable: string; payload: VariableOverrideRequest }) =>
      api.overrideVariable(id, variable, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflow', id, 'dag'] })
      void queryClient.invalidateQueries({ queryKey: ['workflow', id, 'result'] })
    },
  })
}
