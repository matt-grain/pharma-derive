# Implementation Plan — Phase 14.3: Pipeline API Endpoint + Frontend Diagram

**Date:** 2026-04-11
**Feature:** F02/F03 — API to serve pipeline definition + ReactFlow diagram in the UI
**Agents:** `python-fastapi` (API endpoint), then `vite-react` (frontend component)
**Dependencies:** Phase 14.2 must be complete — `clinical_derivation.yaml` must exist, `load_pipeline` must work.

---

## Part A — Backend API (python-fastapi)

### Context for Subagent

The pipeline YAML config is already parseable via `load_pipeline()` from `src.domain.pipeline_models`. We need a single API endpoint that returns the pipeline definition as JSON so the frontend can render it as a diagram.

**Key files to read first:**
- `src/domain/pipeline_models.py` — `PipelineDefinition`, `StepDefinition`, `StepType`
- `src/api/schemas.py` — existing schema pattern (frozen BaseModel)
- `src/api/routers/data.py` — recent router pattern (for reference)
- `src/api/app.py` — where routers are registered

---

### 1. `src/api/schemas.py` (MODIFY)

**Change:** Add pipeline-related response schemas.

**Add after `DataPreviewResponse` class:**

```python
class PipelineStepOut(BaseModel, frozen=True):
    """A single step in the pipeline definition."""
    id: str
    type: str
    description: str
    agent: str | None = None
    agents: list[str] | None = None
    builtin: str | None = None
    depends_on: list[str] = []
    config: dict[str, str | int | float | bool | list[str]] = {}
    has_sub_steps: bool = False


class PipelineOut(BaseModel, frozen=True):
    """Pipeline definition for the frontend diagram."""
    name: str
    version: str
    description: str
    steps: list[PipelineStepOut]
```

**Constraints:**
- `has_sub_steps` is a boolean flag (frontend doesn't need the full sub_step tree — it just shows a "compound" node)
- `type` is `str` not `StepType` enum — the schema layer uses plain strings (matching existing pattern where `status` fields are `str`)
- `config` dict matches `StepDefinition.config` type

---

### 2. `src/api/routers/pipeline.py` (NEW)

**Purpose:** Single endpoint returning the pipeline definition.

```python
"""Pipeline endpoint — serves the pipeline YAML definition as JSON."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api.schemas import PipelineOut, PipelineStepOut
from src.domain.pipeline_models import PipelineDefinition, load_pipeline

router = APIRouter(prefix="/api/v1", tags=["pipeline"])

_DEFAULT_PIPELINE_PATH = "config/pipelines/clinical_derivation.yaml"


@router.get("/pipeline", response_model=PipelineOut, status_code=200)
async def get_pipeline() -> PipelineOut:
    """Return the current pipeline definition for UI rendering."""
    try:
        pipeline = load_pipeline(_DEFAULT_PIPELINE_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_pipeline_out(pipeline)


def _to_pipeline_out(pipeline: PipelineDefinition) -> PipelineOut:
    """Convert domain model to API schema."""
    return PipelineOut(
        name=pipeline.name,
        version=pipeline.version,
        description=pipeline.description,
        steps=[
            PipelineStepOut(
                id=s.id,
                type=s.type.value,
                description=s.description,
                agent=s.agent,
                agents=s.agents,
                builtin=s.builtin,
                depends_on=s.depends_on,
                config=s.config,
                has_sub_steps=s.sub_steps is not None and len(s.sub_steps) > 0,
            )
            for s in pipeline.steps
        ],
    )
```

**Constraints:**
- `response_model=PipelineOut` and `status_code=200` on the decorator
- `_DEFAULT_PIPELINE_PATH` is a module constant (not hardcoded inline)
- File must be under 50 lines

---

### 3. `src/api/app.py` (MODIFY)

**Change:** Register the pipeline router.

**Add import:**
```python
from src.api.routers.pipeline import router as pipeline_router
```

**Add to router registration (after `data_router`):**
```python
app.include_router(pipeline_router)
```

---

### 4. `tests/unit/test_api.py` (MODIFY)

**Change:** Add 1 test for the pipeline endpoint.

```python
async def test_get_pipeline_returns_definition(client: AsyncClient) -> None:
    """GET /pipeline returns the default pipeline definition."""
    # Act
    response = await client.get("/api/v1/pipeline")

    # Assert
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert body["name"] == "clinical_derivation"
    steps: list[dict[str, object]] = body["steps"]  # type: ignore[assignment]
    assert len(steps) >= 5
    step_ids = [s["id"] for s in steps]
    assert "parse_spec" in step_ids
    assert "human_review" in step_ids
```

---

## Part B — Frontend Diagram (vite-react)

### Context for Subagent

The frontend already uses **ReactFlow + dagre** for the DAG visualization in `DAGView.tsx`. We'll reuse the same libraries for a pipeline diagram. The pipeline is fetched from `GET /api/v1/pipeline` and rendered as a horizontal flowchart with agent/builtin/gate icons on each node.

**Key files to read first:**
- `frontend/src/components/DAGView.tsx` — ReactFlow + dagre pattern (MUST read for reference)
- `frontend/src/hooks/useWorkflows.ts` — TanStack Query hook pattern
- `frontend/src/lib/api.ts` — API client pattern
- `frontend/src/types/api.ts` — type definitions
- `frontend/src/pages/WorkflowDetailPage.tsx` — tabs structure (to add Pipeline tab)
- `frontend/src/lib/status.ts` — status color utilities

---

### 5. `frontend/src/types/api.ts` (MODIFY)

**Change:** Add pipeline types.

**Add at the end of the file:**
```typescript
export interface PipelineStep {
  id: string
  type: string
  description: string
  agent: string | null
  agents: string[] | null
  builtin: string | null
  depends_on: string[]
  config: Record<string, string | number | boolean | string[]>
  has_sub_steps: boolean
}

export interface Pipeline {
  name: string
  version: string
  description: string
  steps: PipelineStep[]
}
```

---

### 6. `frontend/src/lib/api.ts` (MODIFY)

**Change:** Add pipeline API call.

**Add import of `Pipeline` to the import block at top.**

**Add to the `api` object (after `downloadAdam`):**
```typescript
  getPipeline: (): Promise<Pipeline> =>
    fetchJson<Pipeline>(`${BASE}/pipeline`),
```

---

### 7. `frontend/src/hooks/useWorkflows.ts` (MODIFY)

**Change:** Add `usePipeline` hook.

**Add after `useWorkflowData`:**
```typescript
export function usePipeline() {
  return useQuery({
    queryKey: ['pipeline'],
    queryFn: api.getPipeline,
    staleTime: 300_000, // Pipeline config rarely changes — cache 5 min
  })
}
```

---

### 8. `frontend/src/components/PipelineView.tsx` (NEW)

**Purpose:** ReactFlow diagram showing pipeline steps as nodes connected by dependency edges.

**Full implementation** (follow this exactly):

```tsx
import { useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  type Edge,
  type Node,
} from 'reactflow'
import dagre from '@dagrejs/dagre'
import 'reactflow/dist/style.css'
import { Bot, Cog, GitMerge, Layers, UserCheck } from 'lucide-react'
import type { PipelineStep } from '@/types/api'

type PipelineViewProps = {
  steps: PipelineStep[]
}

const NODE_W = 220
const NODE_H = 80

const STEP_STYLE: Record<string, { icon: typeof Bot; bg: string; border: string }> = {
  agent:        { icon: Bot,       bg: '#eff6ff', border: '#93c5fd' },
  builtin:      { icon: Cog,       bg: '#f8fafc', border: '#cbd5e1' },
  gather:       { icon: GitMerge,  bg: '#f5f3ff', border: '#c4b5fd' },
  parallel_map: { icon: Layers,    bg: '#ecfdf5', border: '#6ee7b7' },
  hitl_gate:    { icon: UserCheck, bg: '#fffbeb', border: '#fcd34d' },
}

function buildLayout(steps: PipelineStep[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 30, ranksep: 80 })

  steps.forEach((s) => g.setNode(s.id, { width: NODE_W, height: NODE_H }))

  const edges: Edge[] = []
  steps.forEach((s) => {
    s.depends_on.forEach((dep) => {
      g.setEdge(dep, s.id)
      edges.push({
        id: `${dep}->${s.id}`,
        source: dep,
        target: s.id,
        animated: true,
        style: { stroke: '#94a3b8', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8', width: 14, height: 14 },
      })
    })
  })

  dagre.layout(g)

  const flowNodes: Node[] = steps.map((s) => {
    const pos = g.node(s.id)
    const style = STEP_STYLE[s.type] ?? STEP_STYLE['builtin']
    return {
      id: s.id,
      type: 'pipeline',
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      data: { step: s },
      style: {
        border: `2px solid ${style.border}`,
        borderRadius: 8,
        background: style.bg,
        width: NODE_W,
        height: NODE_H,
        padding: 0,
      },
    }
  })

  return { nodes: flowNodes, edges }
}

function PipelineNodeContent({ data }: { data: { step: PipelineStep } }) {
  const { step } = data
  const style = STEP_STYLE[step.type] ?? STEP_STYLE['builtin']
  const Icon = style.icon
  const label = step.agent ?? step.agents?.join(' + ') ?? step.builtin ?? step.type

  return (
    <>
      <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
      <div className="flex h-full flex-col justify-between px-3 py-2">
        <div className="flex items-center gap-1.5">
          <Icon size={13} className="shrink-0 text-slate-500" />
          <span className="truncate text-xs font-semibold text-slate-800">{step.id}</span>
        </div>
        {step.description && (
          <p className="truncate text-[10px] text-slate-500">{step.description}</p>
        )}
        <span className="truncate font-mono text-[10px] text-slate-400">{label}</span>
      </div>
      <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
    </>
  )
}

export function PipelineView({ steps }: PipelineViewProps) {
  const nodeTypes = useMemo(() => ({ pipeline: PipelineNodeContent }), [])
  const { nodes, edges } = useMemo(() => buildLayout(steps), [steps])

  return (
    <div className="h-[340px] overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e2e8f0" gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
```

**Constraints:**
- File is ~115 lines — well under 150 limit
- Uses the EXACT same ReactFlow + dagre pattern as `DAGView.tsx` (same imports, same `buildLayout` structure)
- Direction is `LR` (left-to-right) instead of DAGView's `TB` (top-to-bottom)
- Custom node registered as `'pipeline'` via `nodeTypes` memo
- `useMemo` for BOTH nodeTypes and layout (layout depends on `steps` prop)
- Nodes are NOT draggable/connectable/selectable (read-only pipeline view)
- NO `useEffect`, NO `useState`, NO `useNodesState`/`useEdgesState` — since the pipeline is static, `useMemo` is sufficient (unlike DAGView which updates live)
- Handles use `Position.Left` (target) and `Position.Right` (source) for LR flow
- `proOptions={{ hideAttribution: true }}` removes ReactFlow watermark
- Icon lookup uses `STEP_STYLE` const object keyed by step type string

**Reference:** `frontend/src/components/DAGView.tsx` lines 1-89 (imports, buildLayout, node content, export)

---

### 9. `frontend/src/pages/WorkflowDetailPage.tsx` (MODIFY)

**Change:** Add a "Pipeline" tab (6th tab) that shows the pipeline diagram.

**Add imports:**
```typescript
import { PipelineView } from '@/components/PipelineView'
import { usePipeline } from '@/hooks/useWorkflows'
import { Workflow } from 'lucide-react'  // icon for Pipeline tab
```

**Add hook call near other hooks:**
```typescript
const { data: pipeline } = usePipeline()
```

**Add tab trigger after the Data tab trigger (inside TabsList):**
```tsx
<TabsTrigger value="pipeline" className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-500 transition-all data-[selected]:bg-white data-[selected]:text-slate-900 data-[selected]:shadow-sm">
  <Workflow size={15} />
  Pipeline
</TabsTrigger>
```

**Add tab content after the Data TabsContent:**
```tsx
<TabsContent value="pipeline">
  {pipeline ? (
    <PipelineView steps={pipeline.steps} />
  ) : (
    <div className="rounded-xl border border-dashed border-slate-200 py-20 text-center text-sm text-slate-400">
      Pipeline definition not available
    </div>
  )}
</TabsContent>
```

---

## After Implementation

**Backend:**
1. `uv run ruff check . --fix && uv run ruff format . && uv run pyright .`
2. `uv run lint-imports`
3. `uv run pytest tests/unit/test_api.py -v` (verify pipeline endpoint test passes)
4. `uv run pytest` (full suite)

**Frontend:**
1. `cd frontend && npx tsc --noEmit`
2. Start backend + frontend and verify:
   - Navigate to a workflow detail page
   - Click "Pipeline" tab
   - Should see a horizontal flowchart with 6 nodes
   - Nodes should have appropriate icons and colors
