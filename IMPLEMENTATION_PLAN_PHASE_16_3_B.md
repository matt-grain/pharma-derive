# Phase 16.3b — HITL Frontend Dialogs + Wiring

**Agent:** `vite-react`
**Depends on:** Phase 16.3a (plumbing: types, client, hooks, ui/textarea.tsx)
**Runs last in the critical path**

## Goal

Build the 4 dialog components, wire them into `WorkflowHeader` and `CodePanel`, update `WorkflowDetailPage` to pass DAG data, and add component tests.

**Assumes from 16.3a:**
- `frontend/src/components/ui/textarea.tsx` exists (named `Textarea`, forwarded ref).
- `frontend/src/types/api.ts` has `VariableDecision`, `ApprovalRequest`, `RejectionRequest`, `VariableOverrideRequest`.
- `frontend/src/lib/api.ts` has `approveWorkflowWithFeedback`, `rejectWorkflow`, `overrideVariable` functions.
- `frontend/src/hooks/useWorkflows.ts` has `useApproveWorkflowWithFeedback`, `useRejectWorkflow`, `useOverrideVariable` hooks.

**Assumes from 16.3.0:** Vitest + React Testing Library installed, `pnpm test` runs.

---

## Files to create

### `frontend/src/components/RejectDialog.tsx` (NEW)
**Purpose:** Modal dialog for rejecting a workflow with a mandatory reason.
**Props:**
```typescript
type RejectDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (reason: string) => void
  isRejecting: boolean
}
```
**Behavior:**
- Uses shadcn `Dialog`, `Textarea` (from 16.3a), `Button` primitives.
- Textarea is required — disable Confirm when reason is empty or whitespace-only.
- On Confirm, calls `onConfirm(reason.trim())`.
- Shows `"Rejecting..."` on the button when `isRejecting` is true.
**Constraints:**
- One exported component.
- Local `useState<string>('')` for the reason — acceptable because it's ephemeral form state.
- Destructive variant on the confirm button (`variant="destructive"`).
- No direct API calls — parent wires the mutation.
- Under 80 lines.
**Reference:** `frontend/src/components/NewWorkflowDialog.tsx` — same dialog pattern.

### `frontend/src/components/VariableApprovalList.tsx` (NEW)
**Purpose:** Per-variable checkbox list shown inside the approval dialog.
**Props:**
```typescript
type VariableApprovalListProps = {
  variables: DAGNode[]
  decisions: Record<string, boolean>
  onToggle: (variable: string, approved: boolean) => void
}
```
**Behavior:**
- Renders a scrollable list (`max-h-96 overflow-y-auto`).
- Each row: checkbox + variable name + QC verdict badge + short snippet of `approved_code` (first 80 chars).
- Parent owns the `decisions` state.
**Constraints:**
- **Stateless** — receives `decisions` as props, emits `onToggle` events.
- Reuse `StatusBadge` component for QC verdict display.
- Under 60 lines.
**Reference:** `frontend/src/components/StatusBadge.tsx` for verdict color mapping.

### `frontend/src/components/ApprovalDialog.tsx` (NEW)
**Purpose:** Wraps `VariableApprovalList` + optional reason textarea + Approve button. Opens when user clicks "Approve" in the HITL banner.
**Props:**
```typescript
type ApprovalDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  variables: DAGNode[]
  onConfirm: (payload: ApprovalRequest) => void
  isApproving: boolean
}
```
**Behavior:**
- Initialize `decisions` state as `{[var.variable]: true}` (approve-all default).
- Render `<VariableApprovalList>` + optional reason `<Textarea>`.
- On Confirm, build `ApprovalRequest` payload with all per-variable decisions + reason.
**Constraints:**
- Reuse `Dialog` primitives.
- Default all variables to approved — reviewer selectively unchecks to reject specific variables.
- When `variables` prop changes (e.g., on reopen with different data), reset `decisions` state.
- Under 100 lines.

### `frontend/src/components/CodeEditorDialog.tsx` (NEW)
**Purpose:** Modal with a `<Textarea>` pre-populated with the current approved code, lets user edit and save.
**Props:**
```typescript
type CodeEditorDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  variable: string
  currentCode: string
  onSave: (newCode: string, reason: string) => void
  isSaving: boolean
  error: string | null
}
```
**Behavior:**
- Pre-fills code textarea with `currentCode`.
- Reason textarea below (mandatory).
- Save button disabled when code unchanged OR reason empty OR `isSaving` true.
- Shows inline error when parent passes `error` (surface API errors from override endpoint).
**Constraints:**
- Monospace font on the code textarea (`className="font-mono text-xs"`).
- `rows={20}` for the code area.
- **Plain textarea** — no syntax highlighting. Production would use CodeMirror; this is the explicit demo-grade choice.
- Under 120 lines.

### `frontend/src/components/RejectDialog.test.tsx` (NEW)
**Tests to write:**
- `it('should render when open')`
- `it('should disable confirm when reason is empty')`
- `it('should enable confirm when reason has content')`
- `it('should call onConfirm with trimmed reason')`
- `it('should show Rejecting... when isRejecting is true')`
**Pattern:** RTL + `user-event`, no MSW (pure component tests with callback props).
**Queries:** `getByRole('button')`, `getByRole('textbox')`, `getByText`. No class-name assertions.

### `frontend/src/components/ApprovalDialog.test.tsx` (NEW)
**Tests to write:**
- `it('should default all variables to approved')`
- `it('should toggle a variable when its checkbox is clicked')`
- `it('should send per-variable decisions on confirm')`
**Fixture:** Hand-crafted `DAGNode[]` with 3 variables.

### `frontend/src/components/CodeEditorDialog.test.tsx` (NEW)
**Tests to write:**
- `it('should pre-fill code from props')`
- `it('should disable save when code unchanged')`
- `it('should disable save when reason empty')`
- `it('should display error when error prop is set')`
- `it('should call onSave with new code and reason')`

---

## Files to modify

### `frontend/src/components/WorkflowHeader.tsx` (MOD)
**Change:** Replace the single Approve button with Approve + Reject. Mount the new dialogs.
**Exact change:**
- Add new props:
  ```typescript
  dagNodes: DAGNode[]
  onReject: (reason: string) => void
  onApproveWithFeedback: (payload: ApprovalRequest) => void
  isRejecting: boolean
  ```
- **Remove** existing `onApprove: () => void` prop (replaced by `onApproveWithFeedback`).
- Add local state for dialog open/close:
  ```typescript
  const [approvalOpen, setApprovalOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  ```
- Replace the single Approve button with two buttons inside the amber `Alert`:
  - Approve (primary): opens ApprovalDialog
  - Reject (destructive outline): opens RejectDialog
- Mount `<ApprovalDialog>` and `<RejectDialog>` below the Alert, controlled by local state.
**Constraints:**
- Component must stay under 150 lines.
- If local state grows beyond 2 booleans, extract to a `useHitlDialogs()` custom hook.
- Import new types from `@/types/api`.
- Keep existing props (`status`, `workflowId`, `result`, `isApproving`, `onBack`) — additive change.

### `frontend/src/components/CodePanel.tsx` (MOD)
**Change:** Add an "Edit" button next to the approved code view for each variable. Opens `CodeEditorDialog`.
**Exact change:**
- Import `CodeEditorDialog` and `useOverrideVariable`.
- Add local state for dialog + currently-edited variable:
  ```typescript
  const [editingVariable, setEditingVariable] = useState<string | null>(null)
  const overrideMutation = useOverrideVariable(workflowId)
  ```
- Render `<Button size="sm" variant="outline" onClick={() => setEditingVariable(node.variable)}>Edit</Button>` next to the "Approved" heading.
- Mount `<CodeEditorDialog>` controlled by `editingVariable !== null`:
  ```typescript
  <CodeEditorDialog
    open={editingVariable !== null}
    onOpenChange={(open) => !open && setEditingVariable(null)}
    variable={editingVariable ?? ''}
    currentCode={currentNode?.approved_code ?? ''}
    onSave={(newCode, reason) => {
      overrideMutation.mutate(
        { variable: editingVariable!, payload: { new_code: newCode, reason } },
        { onSuccess: () => setEditingVariable(null) },
      )
    }}
    isSaving={overrideMutation.isPending}
    error={overrideMutation.error?.message ?? null}
  />
  ```
**Constraints:**
- Only show the Edit button when `status.awaiting_approval === true` — don't let users edit after audit ran.
- Needs a new prop `workflowId: string` and `status: WorkflowStatus` if not already present (read the file first to confirm).
- On successful override, close the dialog via mutation's `onSuccess` callback.

### `frontend/src/pages/WorkflowDetailPage.tsx` (MOD)
**Change:** Wire up new hooks and pass DAG nodes into `WorkflowHeader`.
**Critical:** `useWorkflowDag(id)` returns `{ data: DAGNode[] | undefined }` — a **flat array**, NOT an object with a `nodes` property. Use `dagNodes ?? []` directly.
**Exact change:**
- Import `useApproveWorkflowWithFeedback`, `useRejectWorkflow` from `@/hooks/useWorkflows`.
- Use the existing `useWorkflowDag(workflowId)` hook (already imported on the page or nearby — read the file to confirm). Destructure as `{ data: dagNodes }`:
  ```typescript
  const { data: dagNodes } = useWorkflowDag(workflowId)
  const approveMutation = useApproveWorkflowWithFeedback(workflowId)
  const rejectMutation = useRejectWorkflow(workflowId)
  ```
- Pass props into `<WorkflowHeader>`:
  ```tsx
  <WorkflowHeader
    status={status}
    workflowId={workflowId}
    result={result}
    dagNodes={dagNodes ?? []}
    isApproving={approveMutation.isPending}
    isRejecting={rejectMutation.isPending}
    onBack={() => navigate('/')}
    onApproveWithFeedback={(payload) => approveMutation.mutate(payload)}
    onReject={(reason) => rejectMutation.mutate({ reason })}
  />
  ```
- Remove the existing `onApprove` prop wiring (the old single-button flow).
**Constraints:**
- `dagNodes ?? []` — flat array, not `dag?.nodes`. The existing `api.getWorkflowDag(id)` returns `Promise<DAGNode[]>` directly, so the hook result is `DAGNode[] | undefined`.
- Read the current file first to confirm which hooks (`useWorkflowDag`, `useWorkflowStatus`, `useWorkflowResult`) are already imported. Add only the missing ones.
- Do NOT break the existing Audit / Data / Status tabs — only touch the header wiring.

---

## Test constraints

- Component tests use Vitest + React Testing Library (installed in 16.3.0).
- User-centric queries: `getByRole`, `getByLabelText`, `getByText`. No class-name assertions.
- Pure component tests (`RejectDialog`, `ApprovalDialog`, `CodeEditorDialog`) — no mocking needed, test via props + callbacks.
- Follow AAA (arrange/act/assert).

## Tooling gate

```bash
cd frontend
pnpm tsc --noEmit
pnpm eslint . --fix
pnpm test
pnpm vite build
```

## Acceptance criteria

1. ✅ 4 dialog components created, each one exported and typed.
2. ✅ Reject button visible in HITL banner when `awaiting_approval=true`, opens dialog with mandatory reason.
3. ✅ Approve button opens the `ApprovalDialog` with per-variable checkboxes defaulting to approved.
4. ✅ Edit button visible on each variable in `CodePanel` when workflow awaits approval; clicking opens `CodeEditorDialog` with current code.
5. ✅ Saving an override triggers the mutation, invalidates `['workflow', id, 'dag']` and `['workflow', id, 'result']`, updates the UI.
6. ✅ Errors from the API (400 invalid code, 404 unknown variable) surface inline in the dialog.
7. ✅ Component tests cover happy + error + edge paths (≥12 new tests).
8. ✅ All type references use `DAGNode` (TS interface), never `DAGNodeOut`.
9. ✅ `pnpm tsc --noEmit`, `pnpm eslint .`, `pnpm test`, `pnpm vite build` all pass.
