# Phase 11.1 — FastAPI REST API Backend

**Depends on:** Nothing (first phase)
**Agent:** `python-fastapi`
**Goal:** Expose the existing orchestrator via a REST API. The orchestrator runs as a background async task; the API provides status polling and HITL approval endpoints. The existing Streamlit UI is NOT removed — the API runs alongside it.

---

## 1. Add dependencies — `pyproject.toml` (MODIFY)

**Change:** Add FastAPI + uvicorn to project dependencies:
```toml
"fastapi>=0.115,<1",
"uvicorn[standard]>=0.34,<1",
```

---

## 2. API Schemas — `src/api/schemas.py` (NEW)

**Purpose:** Request/response Pydantic models for the REST API. Separate from domain models — these are DTOs for the HTTP boundary.

```python
class WorkflowCreateRequest(BaseModel):
    spec_path: str  # relative path to YAML spec
    llm_base_url: str | None = None  # override LLM endpoint

class WorkflowCreateResponse(BaseModel):
    workflow_id: str
    status: str  # "started"
    message: str

class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    status: str  # FSM current state value
    started_at: str | None
    completed_at: str | None
    derived_variables: list[str]
    errors: list[str]

class WorkflowResultResponse(BaseModel):
    """Full result — only available after workflow completes."""
    workflow_id: str
    study: str
    status: str
    derived_variables: list[str]
    qc_summary: dict[str, str]
    audit_summary: dict[str, object] | None
    errors: list[str]
    duration_seconds: float

class AuditRecordOut(BaseModel):
    timestamp: str
    workflow_id: str
    variable: str
    action: str
    agent: str
    details: dict[str, str | int | float | bool | None]

class SpecListItem(BaseModel):
    filename: str
    study: str
    description: str
    derivation_count: int

class DAGNodeOut(BaseModel):
    variable: str
    status: str
    layer: int
    coder_code: str | None
    qc_code: str | None
    qc_verdict: str | None
    approved_code: str | None
    dependencies: list[str]

class HealthResponse(BaseModel):
    status: str  # "ok"
    version: str
    workflows_in_progress: int
```

**Constraints:**
- `from __future__ import annotations` at top
- All fields typed, no `Any`
- Use `str` for enum values at the API boundary (not StrEnum — JSON serialization)
- `frozen=True` on all response models

---

## 3. Workflow Manager — `src/api/workflow_manager.py` (NEW)

**Purpose:** Manages running workflows — starts background tasks, tracks active runs, provides status/result access. This is the bridge between the HTTP layer and the orchestrator.

```python
class WorkflowManager:
    """Manages active workflow runs as background asyncio tasks."""

    def __init__(self) -> None:
        self._active: dict[str, asyncio.Task[WorkflowResult]] = {}
        self._orchestrators: dict[str, DerivationOrchestrator] = {}
        self._sessions: dict[str, AsyncSession] = {}
        self._results: dict[str, WorkflowResult] = {}

    async def start_workflow(
        self, spec_path: str, llm_base_url: str | None = None, output_dir: Path | None = None,
    ) -> str:
        """Create orchestrator, start run as background task, return workflow_id."""
        orch, session = await create_orchestrator(spec_path, llm_base_url, output_dir)
        wf_id = orch.state.workflow_id
        self._orchestrators[wf_id] = orch
        self._sessions[wf_id] = session
        task = asyncio.create_task(self._run_and_cleanup(wf_id, orch, session))
        self._active[wf_id] = task
        return wf_id

    async def _run_and_cleanup(self, wf_id: str, orch: DerivationOrchestrator, session: AsyncSession) -> WorkflowResult:
        """Run orchestrator, commit session, store result."""
        try:
            result = await orch.run()
            await session.commit()
            self._results[wf_id] = result
            return result
        except Exception:
            logger.exception("Workflow {wf_id} background task failed", wf_id=wf_id)
            await session.rollback()
            raise
        finally:
            await session.close()
            self._active.pop(wf_id, None)
            self._sessions.pop(wf_id, None)

    def get_orchestrator(self, workflow_id: str) -> DerivationOrchestrator | None:
        return self._orchestrators.get(workflow_id)

    def get_result(self, workflow_id: str) -> WorkflowResult | None:
        return self._results.get(workflow_id)

    def is_running(self, workflow_id: str) -> bool:
        return workflow_id in self._active

    @property
    def active_count(self) -> int:
        return len(self._active)

    def list_workflow_ids(self) -> list[str]:
        return list({*self._active.keys(), *self._results.keys()})
```

**Constraints:**
- Must be a singleton — instantiated once in the FastAPI lifespan
- Does NOT manage HITL approval (future Phase 11.2 concern)
- Background tasks must handle session lifecycle (commit on success, rollback on error, close always)
**Reference:** `src/factory.py` for `create_orchestrator` pattern.

---

## 4. API Router — `src/api/routers/workflows.py` (NEW)

**Purpose:** HTTP endpoints for workflow lifecycle.

**Endpoints:**

```python
router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])

@router.post("/", response_model=WorkflowCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_workflow(request: WorkflowCreateRequest, manager: WorkflowManagerDep) -> WorkflowCreateResponse:
    """Start a new derivation workflow as a background task."""

@router.get("/", response_model=list[WorkflowStatusResponse])
async def list_workflows(manager: WorkflowManagerDep) -> list[WorkflowStatusResponse]:
    """List all known workflows (active + completed)."""

@router.get("/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(workflow_id: str, manager: WorkflowManagerDep) -> WorkflowStatusResponse:
    """Get current status of a workflow."""

@router.get("/{workflow_id}/result", response_model=WorkflowResultResponse)
async def get_workflow_result(workflow_id: str, manager: WorkflowManagerDep) -> WorkflowResultResponse:
    """Get full result — 404 if not found, 409 if still running."""

@router.get("/{workflow_id}/audit", response_model=list[AuditRecordOut])
async def get_workflow_audit(workflow_id: str, manager: WorkflowManagerDep) -> list[AuditRecordOut]:
    """Get audit trail records for a workflow."""

@router.get("/{workflow_id}/dag", response_model=list[DAGNodeOut])
async def get_workflow_dag(workflow_id: str, manager: WorkflowManagerDep) -> list[DAGNodeOut]:
    """Get DAG nodes with status, code, and QC verdict."""
```

**IMPORTANT — DAG dependencies extraction:**
The existing `DAGNode` model does NOT store dependencies as a field — they're edges in the networkx graph. To build `DAGNodeOut.dependencies`, extract from the graph:
```python
# In the get_workflow_dag endpoint:
dag = orch.state.dag
for variable in dag.execution_order:
    node = dag.get_node(variable)
    deps = list(dag._graph.predecessors(variable))  # networkx predecessors = dependencies
    # Build DAGNodeOut with deps
```
Alternatively, add a helper to `DerivationDAG`:
```python
def get_dependencies(self, variable: str) -> list[str]:
    """Return variables that this variable depends on."""
    return list(self._graph.predecessors(variable))
```
Prefer the helper method approach — avoids accessing private `_graph` from the API layer.

**Constraints:**
- Use `Annotated[WorkflowManager, Depends(get_workflow_manager)]` for DI
- 404 if workflow not found, 409 if result requested but workflow still running
- Response models from `src/api/schemas.py`
- No business logic — delegate to `WorkflowManager`

---

## 5. Specs Router — `src/api/routers/specs.py` (NEW)

**Purpose:** List available transformation specs.

```python
router = APIRouter(prefix="/api/v1/specs", tags=["specs"])

@router.get("/", response_model=list[SpecListItem])
async def list_specs() -> list[SpecListItem]:
    """List available YAML specs in the specs/ directory."""
    # Glob specs/*.yaml, parse metadata from each
```

**Constraints:** Read-only. Parse `metadata.study` and `metadata.description` from each YAML.

---

## 6. Health Router — `src/api/routers/health.py` (NEW)

**Purpose:** Health check endpoint for Docker/K8s probes.

```python
router = APIRouter(tags=["health"])

@router.get("/health", response_model=HealthResponse)
async def health_check(manager: WorkflowManagerDep) -> HealthResponse:
    """Liveness check with active workflow count."""
```

---

## 7. API Dependencies — `src/api/dependencies.py` (NEW)

**Purpose:** FastAPI `Depends()` factories.

```python
WorkflowManagerDep = Annotated[WorkflowManager, Depends(get_workflow_manager)]
```

The `get_workflow_manager` function returns the singleton from `app.state`.

---

## 8. FastAPI App — `src/api/app.py` (NEW)

**Purpose:** FastAPI application factory with lifespan, CORS, router registration.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize WorkflowManager on startup, cleanup on shutdown."""
    app.state.workflow_manager = WorkflowManager()
    yield
    # Cancel any active workflows on shutdown

def create_app() -> FastAPI:
    app = FastAPI(
        title="CDDE API",
        description="Clinical Data Derivation Engine — REST API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(health_router)
    app.include_router(workflows_router)
    app.include_router(specs_router)
    return app

app = create_app()
```

**Constraints:**
- CORS `allow_origins=["*"]` for dev — the plan note says add env-configurable allowed origins for prod
- Lifespan pattern (not `on_event` deprecated)
- Import routers and register them

---

## 9. Package init — `src/api/__init__.py`, `src/api/routers/__init__.py` (NEW)

Empty `__init__.py` files for the package structure.

---

## 10. Settings update — `src/config/settings.py` (MODIFY)

**Change:** Add `api_host`, `api_port`, `cors_origins`, `output_dir` fields:
```python
api_host: str = "0.0.0.0"
api_port: int = 8000
cors_origins: str = "*"  # comma-separated in production
output_dir: str = "output"  # directory for audit trail JSON exports
```

The `WorkflowManager.start_workflow` should use `Path(get_settings().output_dir)` as the default `output_dir`.

---

## 11. Tests — `tests/unit/test_api.py` (NEW)

**Tests to write (using `httpx.AsyncClient`):**
- `test_health_check_returns_ok` — GET /health returns 200 with status "ok"
- `test_list_specs_returns_available_specs` — GET /api/v1/specs/ returns spec list
- `test_start_workflow_returns_202` — POST /api/v1/workflows/ returns 202 with workflow_id
- `test_get_workflow_status_unknown_id_returns_404` — GET /api/v1/workflows/unknown returns 404
- `test_get_result_while_running_returns_409` — returns 409 Conflict

**Fixtures:**
```python
@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    from src.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
```

**Pattern:** AAA markers, `test_<action>_<scenario>_<expected>` naming.
**Dependencies:** Add `httpx>=0.28,<1` to dev deps in pyproject.toml.

---

## 12. Import linter update — `.importlinter` (MODIFY)

**Change:** Add contracts for the new `api` layer:
```ini
[importlinter:contract:api-no-ui]
name = API cannot import from UI
type = forbidden
source_modules = src.api
forbidden_modules = src.ui
```

The API layer may import from: engine (orchestrator), domain (models), config (settings), persistence (via factory DI). It must NOT import from UI.

---

## Verification

1. `uv run ruff check . --fix && uv run ruff format .`
2. `uv run pyright .`
3. `uv run pytest --tb=short -q` — all tests pass
4. `uv run python -c "from src.api.app import app; print(app.title)"` — smoke test
