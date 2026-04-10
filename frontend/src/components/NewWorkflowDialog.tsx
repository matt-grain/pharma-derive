import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useSpecs, useStartWorkflow } from '@/hooks/useWorkflows'

type NewWorkflowDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function NewWorkflowDialog({ open, onOpenChange }: NewWorkflowDialogProps) {
  const navigate = useNavigate()
  const { data: specs, isLoading: specsLoading } = useSpecs()
  const { mutate: startWorkflow, isPending } = useStartWorkflow()
  const [selectedSpec, setSelectedSpec] = useState<string>('')

  function handleSubmit() {
    if (!selectedSpec) return
    startWorkflow(selectedSpec, {
      onSuccess: (data) => {
        onOpenChange(false)
        navigate(`/workflows/${data.workflow_id}`)
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Start New Workflow</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700">Select Specification</label>
            <Select value={selectedSpec} onValueChange={(v) => setSelectedSpec(v ?? '')}>
              <SelectTrigger>
                <SelectValue placeholder={specsLoading ? 'Loading specs...' : 'Choose a spec file'} />
              </SelectTrigger>
              <SelectContent>
                {specs?.map((spec) => (
                  <SelectItem key={spec.filename} value={spec.filename}>
                    <span className="font-medium">{spec.study}</span>
                    <span className="ml-2 text-slate-400">({spec.derivation_count} derivations)</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {selectedSpec && specs && (
            <p className="text-xs text-slate-500">
              {specs.find((s) => s.filename === selectedSpec)?.description}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!selectedSpec || isPending}
            style={{ backgroundColor: '#0f172a' }}
          >
            {isPending ? 'Starting...' : 'Start Workflow'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
