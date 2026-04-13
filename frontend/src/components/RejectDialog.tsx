import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'

type RejectDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (reason: string) => void
  isRejecting: boolean
}

export function RejectDialog({ open, onOpenChange, onConfirm, isRejecting }: RejectDialogProps) {
  const [reason, setReason] = useState('')
  const isDisabled = reason.trim().length === 0 || isRejecting

  function handleConfirm() {
    if (isDisabled) return
    onConfirm(reason.trim())
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Reject Workflow</DialogTitle>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <label className="text-sm font-medium text-slate-700" htmlFor="reject-reason">
            Reason for rejection <span className="text-red-500">*</span>
          </label>
          <Textarea
            id="reject-reason"
            placeholder="Describe the issue that requires rework..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={4}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={isDisabled}>
            {isRejecting ? 'Rejecting...' : 'Confirm Rejection'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
