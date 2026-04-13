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
import { AlertCircle } from 'lucide-react'

type CodeEditorDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  variable: string
  currentCode: string
  onSave: (newCode: string, reason: string) => void
  isSaving: boolean
  error: string | null
}

type EditorBodyProps = Omit<CodeEditorDialogProps, 'open' | 'onOpenChange'>

/**
 * Inner form body — mounted with key={variable} so state resets cleanly
 * when the dialog is opened for a different variable, without needing a useEffect.
 */
function EditorBody({ variable, currentCode, onSave, isSaving, error }: EditorBodyProps) {
  const [code, setCode] = useState(currentCode)
  const [reason, setReason] = useState('')

  const isUnchanged = code === currentCode
  const isSaveDisabled = isUnchanged || reason.trim().length === 0 || isSaving

  function handleSave() {
    if (isSaveDisabled) return
    onSave(code, reason.trim())
  }

  return (
    <>
      <div className="space-y-4 py-2">
        {/* Plain textarea — production would use CodeMirror */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-slate-700" htmlFor={`code-editor-${variable}`}>
            Code
          </label>
          <Textarea
            id={`code-editor-${variable}`}
            className="font-mono text-xs"
            rows={20}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-slate-700" htmlFor={`edit-reason-${variable}`}>
            Reason for change <span className="text-red-500">*</span>
          </label>
          <Textarea
            id={`edit-reason-${variable}`}
            placeholder="Describe why this code was modified..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
          />
        </div>
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>
      <DialogFooter>
        <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
        <Button onClick={handleSave} disabled={isSaveDisabled}>
          {isSaving ? 'Saving...' : 'Save Override'}
        </Button>
      </DialogFooter>
    </>
  )
}

export function CodeEditorDialog({
  open,
  onOpenChange,
  variable,
  currentCode,
  onSave,
  isSaving,
  error,
}: CodeEditorDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit Code — {variable}</DialogTitle>
        </DialogHeader>
        {/* key resets inner state when variable changes (new dialog open) */}
        <EditorBody
          key={variable}
          variable={variable}
          currentCode={currentCode}
          onSave={onSave}
          isSaving={isSaving}
          error={error}
        />
      </DialogContent>
    </Dialog>
  )
}
