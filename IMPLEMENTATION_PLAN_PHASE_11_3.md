# Phase 11.3 — Vite + React SPA Frontend

**Depends on:** Phase 11.1 (REST API endpoints must exist for the frontend to call)
**Agent:** `vite-react`
**Goal:** Build a production-grade React SPA that replaces the Streamlit UI. 5 pages, calling the FastAPI backend at `/api/v1/`. Uses shadcn/ui components, Tailwind CSS, and reactflow for DAG visualization.

**IMPORTANT:** This is a NEW sub-project in `frontend/`. It has its own `package.json`, `tsconfig.json`, `vite.config.ts`. It does NOT touch the Python codebase.

**Design skill:** Use the `frontend-design` skill from `.claude/skills/frontend-design/SKILL.md` for design guidance. The aesthetic direction for this app:
- **Tone:** Clinical precision meets modern data platform — think "Bloomberg terminal for pharma data scientists." Not playful, not generic SaaS.
- **Color palette:** Deep navy primary (#0f172a), white content (#ffffff), emerald accents for success/approved (#10b981), amber for warnings/mismatch (#f59e0b), red for failures (#ef4444). Subtle blue-gray for secondary (#64748b).
- **Typography:** JetBrains Mono for code blocks, system sans-serif for UI (fast loading, familiar to technical users).
- **Layout:** Dense but organized — data tables, code panels, status dashboards. Not marketing-page spacing.
- **Key differentiator:** The interactive DAG visualization with reactflow — this is the demo showpiece. Make it look impressive with smooth animations, color-coded nodes by derivation status, and a clean layered layout.

---

## 1. Project Scaffold — `frontend/` (NEW directory)

Initialize with Vite + React + TypeScript template. The agent should run:
```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install -D tailwindcss @tailwindcss/vite
npm install @tanstack/react-query lucide-react reactflow react-router-dom @dagrejs/dagre
npm install -D @types/dagre
```

**Note:** `react-router-dom` v7+ includes its own TypeScript types — no `@types` package needed.

Then set up shadcn/ui:
```bash
npx shadcn@latest init
npx shadcn@latest add card badge button table tabs input select separator alert dialog
```

**Key config files:**
- `frontend/vite.config.ts` — proxy `/api` to backend (port 8000)
- `frontend/tsconfig.json` — strict mode, path aliases
- `frontend/tailwind.config.ts` — extend with project colors

**Vite proxy config (critical for dev):**
```typescript
// vite.config.ts
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/mcp': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
```

---

## 2. API Client — `frontend/src/lib/api.ts` (NEW)

**Purpose:** Typed API client wrapping fetch calls to the backend.

```typescript
const BASE = '/api/v1'

export async function startWorkflow(specPath: string): Promise<{ workflow_id: string; status: string }>
export async function getWorkflowStatus(id: string): Promise<WorkflowStatus>
export async function getWorkflowResult(id: string): Promise<WorkflowResult>
export async function getWorkflowAudit(id: string): Promise<AuditRecord[]>
export async function getWorkflowDag(id: string): Promise<DAGNode[]>
export async function listSpecs(): Promise<SpecItem[]>
export async function healthCheck(): Promise<{ status: string; version: string }>
```

**Constraints:**
- All functions throw on non-2xx responses (let React Query handle errors)
- Return typed objects matching the API schemas
- No `any` — use typed interfaces

---

## 3. Types — `frontend/src/types/api.ts` (NEW)

**Purpose:** TypeScript interfaces matching the FastAPI response schemas.

```typescript
export interface WorkflowStatus {
  workflow_id: string
  status: string
  started_at: string | null
  completed_at: string | null
  derived_variables: string[]
  errors: string[]
}

export interface WorkflowResult {
  workflow_id: string
  study: string
  status: string
  derived_variables: string[]
  qc_summary: Record<string, string>
  audit_summary: Record<string, unknown> | null
  errors: string[]
  duration_seconds: number
}

export interface AuditRecord {
  timestamp: string
  workflow_id: string
  variable: string
  action: string
  agent: string
  details: Record<string, string | number | boolean | null>
}

export interface DAGNode {
  variable: string
  status: string
  layer: number
  coder_code: string | null
  qc_code: string | null
  qc_verdict: string | null
  approved_code: string | null
  dependencies: string[]
}

export interface SpecItem {
  filename: string
  study: string
  description: string
  derivation_count: number
}
```

---

## 4. React Query Hooks — `frontend/src/hooks/useWorkflows.ts` (NEW)

**Purpose:** TanStack Query hooks wrapping the API client.

```typescript
export function useSpecs(): UseQueryResult<SpecItem[]>
export function useWorkflowStatus(id: string): UseQueryResult<WorkflowStatus>  // polls every 2s while running
export function useWorkflowResult(id: string): UseQueryResult<WorkflowResult>
export function useWorkflowAudit(id: string): UseQueryResult<AuditRecord[]>
export function useWorkflowDag(id: string): UseQueryResult<DAGNode[]>
export function useStartWorkflow(): UseMutationResult<{workflow_id: string}, Error, {specPath: string}>
```

**Constraints:**
- `useWorkflowStatus` uses `refetchInterval: 2000` while status is not terminal
- Mutations via `useMutation`, not raw fetch in event handlers
- All hooks in one file (they're thin wrappers)

---

## 5. Layout — `frontend/src/components/Layout.tsx` (NEW)

**Purpose:** App shell with sidebar navigation and header.

- Sidebar: links to Dashboard, Specs, Audit Trail
- Header: "CDDE" title + health indicator (green/red dot)
- Main content area with `<Outlet />`

Use shadcn/ui `Button` for nav items, `Badge` for health status.
Design: clean, clinical, minimal — dark sidebar (#1e293b), white content area.

---

## 6. Pages (5 pages)

### 6a. Dashboard — `frontend/src/pages/DashboardPage.tsx` (NEW)

**Purpose:** Overview of all workflows — active + completed. Start new runs.

- Card grid showing each workflow: ID, status badge (colored by state), duration, variable count
- "New Workflow" button → opens dialog to select spec and start run
- Active workflows auto-refresh via `useWorkflowStatus` polling
- Completed workflows show QC summary stats

**Components to extract:**
- `WorkflowCard.tsx` — single workflow status card
- `NewWorkflowDialog.tsx` — spec selector + start button

### 6b. Workflow Detail — `frontend/src/pages/WorkflowDetailPage.tsx` (NEW)

**Purpose:** Deep dive into a single workflow run. Tabbed interface.

**Tabs:**
1. **Status** — FSM state, timing, errors, derived variables list
2. **DAG** — Interactive graph using reactflow (nodes = variables, edges = dependencies, colors by status)
3. **Code** — Per-variable code view: coder code, QC code, approved code side-by-side
4. **Audit** — Chronological audit trail for this workflow

**URL:** `/workflows/:id` — uses `useParams` to extract workflow_id

### 6c. DAG View Component — `frontend/src/components/DAGView.tsx` (NEW)

**Purpose:** Interactive DAG visualization using reactflow.

- Nodes: variable name + status badge (green=approved, red=mismatch, gray=pending)
- Edges: dependency arrows
- Click node → expand to show code + QC verdict in a panel
- Layout: dagre algorithm (top-to-bottom, layered)

**Dependencies:** `reactflow`, `dagre` (for layout)

### 6d. Specs Page — `frontend/src/pages/SpecsPage.tsx` (NEW)

**Purpose:** List available specs, show derivation count, trigger workflow.

- Table with columns: Study, Description, Derivations, Actions
- "Run" button per spec → starts workflow, navigates to detail page

### 6e. Audit Trail Page — `frontend/src/pages/AuditPage.tsx` (NEW)

**Purpose:** Global audit view across all completed workflows.

- Dropdown to select workflow run
- Filterable table of audit records (by variable, by agent, by action)
- Download audit JSON button
- Timeline visualization (optional — vertical timeline with colored dots per action)

---

## 7. Router — `frontend/src/App.tsx` (NEW)

**Purpose:** React Router setup with layout.

```typescript
<Routes>
  <Route element={<Layout />}>
    <Route index element={<DashboardPage />} />
    <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
    <Route path="/specs" element={<SpecsPage />} />
    <Route path="/audit" element={<AuditPage />} />
  </Route>
</Routes>
```

Wrap with `<QueryClientProvider>` from TanStack Query.

---

## 8. Entry point — `frontend/src/main.tsx` (MODIFY from Vite template)

**Change:** Add QueryClientProvider, BrowserRouter, import global CSS.

---

## Verification

1. `cd frontend && npm run build` — production build succeeds
2. `npm run lint` (if ESLint configured)
3. `npm run dev` — dev server starts on :3000, proxies to :8000
4. Visual check: dashboard loads, spec list works, DAG renders
