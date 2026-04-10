import { AlertTriangle } from 'lucide-react'
import { getStatusColor, getStatusLabel, STATUS_BADGE_CLASSES } from '@/lib/status'

type StatusBadgeProps = {
  status: string
  className?: string
}

export function StatusBadge({ status, className = '' }: StatusBadgeProps) {
  const color = getStatusColor(status)
  const classes = STATUS_BADGE_CLASSES[color]

  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium ${classes} ${className}`}
    >
      {status === 'review' && <AlertTriangle size={11} />}
      {status === 'review' ? 'Awaiting Approval' : getStatusLabel(status)}
    </span>
  )
}
