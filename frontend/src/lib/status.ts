// Centralized status palette — all status-to-color mappings live here.
// Palette: emerald=approved, amber=in-progress, red=failed, gray=pending

export type StatusColor = 'emerald' | 'amber' | 'red' | 'gray' | 'blue'

export const TERMINAL_STATUSES = ['completed', 'failed'] as const

const STATUS_COLOR_MAP: Record<string, StatusColor> = {
  approved: 'emerald',
  completed: 'emerald',
  passed: 'emerald',
  in_progress: 'amber',
  verifying: 'amber',
  running: 'amber',
  review: 'amber',
  deriving: 'amber',
  debugging: 'amber',
  qc_mismatch: 'red',
  failed: 'red',
  error: 'red',
  pending: 'gray',
  not_started: 'gray',
  created: 'blue',
  spec_review: 'blue',
  dag_built: 'blue',
}

export function getStatusColor(status: string): StatusColor {
  return STATUS_COLOR_MAP[status] ?? 'gray'
}

export const STATUS_BADGE_CLASSES: Record<StatusColor, string> = {
  emerald: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  amber: 'bg-amber-100 text-amber-800 border-amber-200',
  red: 'bg-red-100 text-red-800 border-red-200',
  gray: 'bg-slate-100 text-slate-600 border-slate-200',
  blue: 'bg-blue-100 text-blue-800 border-blue-200',
}

export const STATUS_DOT_CLASSES: Record<StatusColor, string> = {
  emerald: 'bg-emerald-500',
  amber: 'bg-amber-500',
  red: 'bg-red-500',
  gray: 'bg-slate-400',
  blue: 'bg-blue-500',
}

export const STATUS_NODE_BORDER: Record<StatusColor, string> = {
  emerald: '#10b981',
  amber: '#f59e0b',
  red: '#ef4444',
  gray: '#94a3b8',
  blue: '#3b82f6',
}

export function getStatusLabel(status: string): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
