import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { TERMINAL_STATUSES } from '@/lib/status'

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
