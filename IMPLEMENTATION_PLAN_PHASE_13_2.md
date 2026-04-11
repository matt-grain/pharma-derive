# Implementation Plan — Phase 13.2: Frontend Data Tab

**Date:** 2026-04-11
**Feature:** F07 — ADaM Data Output (frontend)
**Agent:** `vite-react`
**Dependencies:** Phase 13.1 must be complete — the backend `GET /api/v1/workflows/{id}/data` endpoint must exist and return `DataPreviewResponse`.

---

## Context for Subagent

This is a Vite + React SPA (internal tool) for a Clinical Data Derivation Engine. The frontend lives in `frontend/`. It uses:
- **TanStack Query** for server state (all API hooks in `frontend/src/hooks/useWorkflows.ts`)
- **shadcn/ui** components (Tabs, Button, Badge, etc.)
- **Tailwind CSS** for styling
- **TypeScript strict mode** (`noUncheckedIndexedAccess: true`)

The WorkflowDetailPage (`frontend/src/pages/WorkflowDetailPage.tsx`) has 4 tabs: Status, DAG, Code, Audit. We are adding a 5th "Data" tab that shows:
1. Source SDTM data preview (columns + sample rows)
2. Derived ADaM data preview (columns + sample rows)
3. Download buttons for CSV and Parquet formats

**Key files to read first:**
- `frontend/src/pages/WorkflowDetailPage.tsx` — the page we're adding the tab to (lines 122-159 for tab structure)
- `frontend/src/components/StatusTab.tsx` — reference for tab component pattern (40 lines, clean)
- `frontend/src/components/AuditTable.tsx` — reference for table component pattern
- `frontend/src/hooks/useWorkflows.ts` — all TanStack Query hooks (follow the same pattern)
- `frontend/src/lib/api.ts` — API client functions (follow the same pattern)
- `frontend/src/types/api.ts` — all API response types

---

## Files to Modify

### 1. `frontend/src/types/api.ts` (MODIFY)

**Change:** Add types for the data preview API response.

**Add at the end of the file (after `StartWorkflowResponse`):**

```typescript
export interface ColumnInfo {
  name: string
  dtype: string
  null_count: number
  sample_values: (string | number | null)[]
}

export interface DatasetPreview {
  label: string
  row_count: number
  column_count: number
  columns: ColumnInfo[]
  rows: Record<string, string | number | null>[]
}

export interface DataPreviewResponse {
  workflow_id: string
  source: DatasetPreview | null
  derived: DatasetPreview | null
  derived_formats: string[]
}
```

**Constraints:**
- These types mirror the backend Pydantic schemas exactly (field names use snake_case — matching the JSON response)
- `sample_values` uses union type `(string | number | null)[]` — not `unknown[]`
- `rows` uses `Record<string, string | number | null>[]` — not `unknown[]`

---

### 2. `frontend/src/lib/api.ts` (MODIFY)

**Change:** Add two API functions — one for data preview, one for triggering download.

**Add import** of the new type at the top:
```typescript
import type {
  // ... existing imports
  DataPreviewResponse,
} from '@/types/api'
```

**Add to the `api` object (after `getWorkflowDag`):**

```typescript
  getWorkflowData: (id: string, limit = 50): Promise<DataPreviewResponse> =>
    fetchJson<DataPreviewResponse>(`${BASE}/workflows/${id}/data?limit=${limit}`),

  downloadAdam: async (id: string, format: 'csv' | 'parquet' = 'csv'): Promise<void> => {
    const res = await fetch(`${BASE}/workflows/${id}/adam?format=${format}`)
    if (!res.ok) throw new Error(`API error ${res.status}: ${res.statusText}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${id}_adam.${format}`
    a.click()
    URL.revokeObjectURL(url)
  },
```

**Constraints:**
- `getWorkflowData` uses `fetchJson` (existing helper) — returns typed JSON
- `downloadAdam` does NOT use `fetchJson` — it needs the raw blob for file download. It creates a temporary link to trigger the browser download dialog.
- The `limit` param defaults to 50 to match the backend default

---

### 3. `frontend/src/hooks/useWorkflows.ts` (MODIFY)

**Change:** Add a `useWorkflowData` hook.

**Add after `useWorkflowDag` (line ~64):**

```typescript
export function useWorkflowData(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ['workflow', id, 'data'],
    queryFn: () => api.getWorkflowData(id),
    enabled,
    staleTime: 60_000, // Data preview is static once workflow completes — cache 1 min
  })
}
```

**Constraints:**
- `enabled` param controls when to fetch — only fetch when workflow is in a terminal state (completed/failed) since data is only available after derivation
- Use `staleTime: 60_000` — data preview doesn't change once a workflow completes, so avoid unnecessary refetches
- Follow the same pattern as `useWorkflowResult` (also uses `enabled` param)

---

### 4. `frontend/src/components/DataTab.tsx` (NEW)

**Purpose:** Display source SDTM and derived ADaM data in a side-by-side preview with column metadata and a scrollable data table, plus download buttons.

**Props:**
```typescript
type DataTabProps = {
  workflowId: string
  data: DataPreviewResponse | undefined
  isLoading: boolean
}
```

**Component structure:**

```
DataTab
├── Download buttons row (CSV + Parquet, only if derived_formats includes them)
├── Grid (2 columns on desktop, stacked on mobile)
│   ├── Source panel (if data.source exists)
│   │   ├── Header: "SDTM (Source)" + row/col counts
│   │   ├── Column metadata cards (name, dtype, nulls)
│   │   └── Scrollable data table (first 50 rows)
│   └── Derived panel (if data.derived exists)
│       ├── Header: "ADaM (Derived)" + row/col counts
│       ├── Column metadata cards
│       └── Scrollable data table (first 50 rows)
└── Empty state (if neither source nor derived available)
```

**Implementation details:**

1. **Download buttons:** Use `api.downloadAdam()` directly in onClick handlers. Show buttons only when `data?.derived_formats` includes the format. Use the shadcn `Button` component with `variant="outline"` and a download icon from Lucide.

2. **Dataset panel:** Extract a `DatasetPanel` sub-component (not exported, co-located in the same file) that takes a `DatasetPreview` and renders the column info + table:

```typescript
function DatasetPanel({ dataset }: { dataset: DatasetPreview }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      {/* Header with label + counts */}
      {/* Column metadata: horizontal scroll of small cards */}
      {/* Data table: use <table> with horizontal scroll for many columns */}
    </div>
  )
}
```

3. **Data table:** Use a plain HTML `<table>` with `overflow-x-auto` wrapper. No need for TanStack Table — this is a read-only preview with max 50 rows. Columns come from `dataset.columns[].name`. Rows come from `dataset.rows[]`.

4. **Column cards:** Small cards showing `name`, `dtype` as a badge, and `{null_count} nulls` as a count. Use `flex flex-wrap gap-2` layout.

5. **Loading state:** Show a skeleton/spinner when `isLoading` is true.

6. **Empty state:** Show "Data not yet available" dashed border box (same pattern as DAG empty state in WorkflowDetailPage line 138).

**Constraints:**
- File must be under 150 lines. If it grows, the `DatasetPanel` sub-component is the extraction point.
- No `useEffect` — data is passed as props from the parent via TanStack Query
- No `useState` for server data — the preview data comes from the `useWorkflowData` hook in the parent
- Use `import { api } from '@/lib/api'` for the download function (direct call in onClick, not through a mutation hook — downloads are fire-and-forget)
- Format null/NaN values as `—` (em-dash) in the table cells, not "null" or empty string
- Truncate long cell values to ~30 chars with ellipsis for readability

**Reference files:**
- `frontend/src/components/StatusTab.tsx` — for the tab component structure (props pattern, card layout)
- `frontend/src/components/AuditTable.tsx` — for table rendering pattern
- `frontend/src/pages/WorkflowDetailPage.tsx:136-140` — for empty state pattern

---

### 5. `frontend/src/pages/WorkflowDetailPage.tsx` (MODIFY)

**Change 1:** Import the new hook and component.

**Add imports:**
```typescript
import { DataTab } from '@/components/DataTab'
import { useWorkflowData } from '@/hooks/useWorkflows'  // add to existing import
```

Actually, `useWorkflowData` should be added to the existing import line:
```typescript
// Change this:
import { useWorkflowStatus, useWorkflowResult, useWorkflowAudit, useWorkflowDag, useApproveWorkflow } from '@/hooks/useWorkflows'
// To this:
import { useWorkflowStatus, useWorkflowResult, useWorkflowAudit, useWorkflowDag, useWorkflowData, useApproveWorkflow } from '@/hooks/useWorkflows'
```

**Change 2:** Add the hook call near the other hooks.

Find where hooks are called (around lines 20-30) and add:
```typescript
const { data: dataPreview, isLoading: isDataLoading } = useWorkflowData(
  id,
  TERMINAL_STATUSES.includes(status?.status ?? ''),
)
```

**Note:** `TERMINAL_STATUSES` is already imported in this file (from `@/lib/status`). The `enabled` condition ensures we only fetch data preview when the workflow has completed or failed.

**Change 3:** Add the "Data" tab trigger and content.

In the `<TabsList>` (around line 123-128), add a new trigger:
```tsx
<TabsTrigger value="data">Data</TabsTrigger>
```

Add it AFTER the "Audit" trigger (so the order is: Status, DAG, Code, Audit, Data).

Add the tab content AFTER the Audit `<TabsContent>` (after line 158):
```tsx
<TabsContent value="data">
  <DataTab
    workflowId={id}
    data={dataPreview}
    isLoading={isDataLoading}
  />
</TabsContent>
```

**Constraints:**
- The page is already 163 lines — adding ~10 lines keeps it under 180, acceptable
- The Data tab is last in the order (Status → DAG → Code → Audit → Data) since it's the output artifact, viewed after inspecting the process
- `enabled` on the hook prevents unnecessary API calls for in-progress workflows

---

## After Implementation

1. Run: `cd frontend && npx tsc --noEmit`
2. Run: `cd frontend && npx eslint . --fix` (if eslint is configured)
3. Verify visually:
   - Start the backend: `uv run python -m src.api.app`
   - Start the frontend: `cd frontend && npm run dev`
   - Navigate to a completed workflow
   - Click the "Data" tab — should show source and derived panels
   - Click download buttons — should trigger file download
4. Test edge cases:
   - Workflow still in progress — Data tab should show empty state
   - Workflow failed — Data tab may show partial data or empty state
   - No parquet file — only CSV download button should appear
