# Phase 16.3a — HITL Frontend Plumbing (types, client, hooks, primitives)

**Agent:** `vite-react`
**Depends on:** Phase 16.3.0 (test infra), Phase 16.2b (API surface)
**Runs before:** Phase 16.3b (dialogs + wiring)

## Goal

Set up the non-visual plumbing that Phase 16.3b dialogs depend on:
1. `ui/textarea.tsx` shadcn primitive (missing from the repo).
2. TypeScript types for new API payloads.
3. Typed API client functions in `lib/api.ts`.
4. TanStack mutation hooks in `useWorkflows.ts`.

All of this can be implemented and type-checked without any dialog component or page wiring — those come in 16.3b.

**Key verified facts** (from codebase scan — match these EXACTLY, do not reinvent):
- TypeScript DAG type is named `DAGNode` in `frontend/src/types/api.ts:37` — **NOT `DAGNodeOut`**.
- Query keys are **inline arrays** in `useWorkflows.ts` (`['workflow', id]`, etc.). No `workflowKeys` const.
- `frontend/src/components/ui/` has NO textarea primitive — this phase adds it.
- `@/lib/utils` has `cn()` helper used by other `ui/*.tsx` primitives.
- **`lib/api.ts` uses a `const api = { ... }` object pattern**, not top-level async functions. The private helper is named `fetchJson<T>`, NOT `apiClient<T>`. Existing methods look like: `approveWorkflow: (id: string): Promise<WorkflowStatus> => fetchJson<WorkflowStatus>(...)`. New methods must be added as properties on the `api` object.
- **`useWorkflowDag(id)` returns `Promise<DAGNode[]>` directly** — the response is a flat array, NOT wrapped in `{ nodes: DAGNode[] }`. The React hook returns `{ data: DAGNode[] | undefined }`.
- Existing `api.approveWorkflow(id)` (no body) stays — backwards compat — but we add a new `api.approveWorkflowWithFeedback(id, payload)` method for the new flow.
- `api.deleteWorkflow` uses `await fetch()` directly (for void return) — do not use `fetchJson` for endpoints that return `void` or a non-JSON body.

---

## Files to create

### `frontend/src/components/ui/textarea.tsx` (NEW — shadcn primitive)
**Purpose:** Shadcn Textarea primitive, used by all 3 dialogs in Phase 16.3b.
**Content:**
```tsx
import * as React from 'react'
import { cn } from '@/lib/utils'

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        'flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  ),
)
Textarea.displayName = 'Textarea'
```
**Constraints:**
- Uses existing `cn` helper at `@/lib/utils`.
- `forwardRef` so React Hook Form or parent refs work.
- Export as named export, matches existing `ui/*.tsx` style.
**Reference:** `frontend/src/components/ui/input.tsx` — mirror its structure.

---

## Files to modify

### `frontend/src/types/api.ts` (MOD)
**Change:** Append 4 new types for the HITL payloads.
**Exact change:**
```typescript
export type VariableDecision = {
  variable: string
  approved: boolean
  note: string | null
}

export type ApprovalRequest = {
  variables: VariableDecision[]
  reason: string | null
}

export type RejectionRequest = {
  reason: string
}

export type VariableOverrideRequest = {
  new_code: string
  reason: string
}
```
**Constraints:**
- Match existing file style (no semicolons are fine — check the top of the file and mirror).
- Types mirror the Python Pydantic schemas in `src/api/schemas.py` added by Phase 16.2b.

### `frontend/src/lib/api.ts` (MOD)
**Change:** Add 3 methods as properties on the existing `api` object. Do NOT create top-level async functions — match the existing pattern.
**Exact change:**

1. Add `ApprovalRequest`, `RejectionRequest`, `VariableOverrideRequest` to the `import type` block at the top of the file (alongside the existing imports from `@/types/api`).

2. Inside the `export const api = { ... }` object, after the existing `rerunWorkflow` method (line ~93), append these 3 new methods (each as an arrow function property, matching the style of existing methods):
```typescript
  approveWorkflowWithFeedback: (id: string, payload: ApprovalRequest): Promise<WorkflowStatus> =>
    fetchJson<WorkflowStatus>(`${BASE}/workflows/${id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  rejectWorkflow: (id: string, payload: RejectionRequest): Promise<WorkflowStatus> =>
    fetchJson<WorkflowStatus>(`${BASE}/workflows/${id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  overrideVariable: (id: string, variable: string, payload: VariableOverrideRequest): Promise<DAGNode> =>
    fetchJson<DAGNode>(`${BASE}/workflows/${id}/variables/${variable}/override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
```
**Constraints:**
- **Match the existing pattern exactly.** Methods go INSIDE the `api` object literal, as arrow-function properties.
- Use the existing `fetchJson<T>` helper, NOT a made-up `apiClient<T>`.
- Include the `Content-Type` header on all POST calls with JSON body (matches existing `startWorkflow` pattern on line 47).
- `BASE` is the module-level `const BASE = '/api/v1'` already declared at line 13.
- Do NOT rename `fetchJson`, do NOT add any new top-level functions.
- Response type for `overrideVariable` is `DAGNode`, not `DAGNodeOut`.
- Existing `approveWorkflow` method stays untouched (backwards compat for callers that pass no payload).

### `frontend/src/hooks/useWorkflows.ts` (MOD)
**Change:** Append 3 new TanStack mutation hooks. All call methods on the `api` object (NOT top-level functions). Use the existing inline query-key pattern.
**Exact change:**

1. Add types to the existing type imports at the top if not already present:
```typescript
import type { ApprovalRequest, RejectionRequest, VariableOverrideRequest } from '@/types/api'
```
(Or add them alongside the existing `api` import from `@/lib/api` — whichever matches the current structure.)

2. Append after the existing `useRerunWorkflow` hook:
```typescript
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
```
**Constraints:**
- **All mutationFn bodies call `api.<method>(...)`**, never a bare function name. This matches the existing hooks in this file (e.g., `useApproveWorkflow` calls `api.approveWorkflow(id)`).
- Inline array query keys (`['workflow', id]`, `['workflow', id, 'dag']`, etc.) — no `workflowKeys` const.
- `void` prefix on `invalidateQueries` to satisfy ESLint's `no-floating-promises`.
- The hook parameter is conventionally named `id` (matches `useApproveWorkflow` on line 93), not `workflowId`.
- No new global state, no new module-level constants.

---

## Tooling gate

```bash
cd frontend
pnpm tsc --noEmit
pnpm eslint . --fix
pnpm vite build
pnpm test  # still "no tests found" — that's fine, tests arrive in 16.3b
```

## Acceptance criteria

1. ✅ `ui/textarea.tsx` compiles and exports a `Textarea` forwarded-ref component.
2. ✅ 4 new types added to `types/api.ts`, all exported, no `any`.
3. ✅ 3 new typed client functions in `lib/api.ts`, all return typed promises.
4. ✅ 3 new mutation hooks in `useWorkflows.ts`, all use inline array query keys.
5. ✅ `pnpm tsc --noEmit` clean.
6. ✅ `pnpm vite build` succeeds.
7. ✅ No new ESLint warnings.
8. ✅ No dialog components, no page wiring, no tests yet — those come in 16.3b.
