import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { VariableApprovalList } from '@/components/VariableApprovalList'
import type { DAGNode, ApprovalRequest } from '@/types/api'

type ApprovalDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  variables: DAGNode[]
  onConfirm: (payload: ApprovalRequest) => void
  isApproving: boolean
}

type ApprovalDialogBodyProps = Omit<ApprovalDialogProps, 'open' | 'onOpenChange'>

/**
 * Inner form body — mounted with a stable key so state resets cleanly when
 * the dialog is reopened with fresh variables, without needing a useEffect.
 */
function ApprovalDialogBody({ variables, onConfirm, isApproving }: ApprovalDialogBodyProps) {
  const [decisions, setDecisions] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(variables.map((v) => [v.variable, true])),
  )
  const [reason, setReason] = useState('')

  function handleToggle(variable: string, approved: boolean) {
    setDecisions((prev) => ({ ...prev, [variable]: approved }))
  }

  function handleConfirm() {
    const payload: ApprovalRequest = {
      variables: variables.map((v) => ({
        variable: v.variable,
        approved: decisions[v.variable] ?? true,
        note: null,
      })),
      reason: reason.trim() || null,
    }
    onConfirm(payload)
  }

  return (
    <>
      <div className="space-y-4 py-2">
        <p className="text-xs text-slate-500">
          All variables default to approved. Uncheck any that need rework.
        </p>
        <VariableApprovalList
          variables={variables}
          decisions={decisions}
          onToggle={handleToggle}
        />
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-slate-700" htmlFor="approval-reason">
            Optional notes
          </label>
          <Textarea
            id="approval-reason"
            placeholder="Add reviewer notes (optional)..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
          />
        </div>
      </div>
      <DialogFooter>
        <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
        <Button
          className="bg-emerald-600 hover:bg-emerald-700"
          onClick={handleConfirm}
          disabled={isApproving}
        >
          {isApproving ? 'Approving...' : 'Approve & Run Audit'}
        </Button>
      </DialogFooter>
    </>
  )
}

export function ApprovalDialog({
  open,
  onOpenChange,
  variables,
  onConfirm,
  isApproving,
}: ApprovalDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Approve Workflow</DialogTitle>
        </DialogHeader>
        {/* key resets inner state when variables change (e.g. dialog reopens) */}
        <ApprovalDialogBody
          key={variables.map((v) => v.variable).join(',')}
          variables={variables}
          onConfirm={onConfirm}
          isApproving={isApproving}
        />
      </DialogContent>
    </Dialog>
  )
}
