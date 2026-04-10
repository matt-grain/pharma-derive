# Phase 10.1 — Foundation: New Types + Module Restructure

**Depends on:** Nothing (first phase)
**Agent:** `python-fastapi`
**Refactoring items:** R07, R08, R09, R10 (+ R01 partial: add exception classes)
**Goal:** Create all new types, packages, and module moves. No behavioral changes yet — existing code continues to work via updated imports.

---

## 1. New Domain Exceptions — `src/domain/exceptions.py` (NEW)

**Purpose:** Domain-specific exceptions replacing `assert` guards and providing structured error context.
**Fields/Classes:**
```python
class CDDEError(Exception):
    """Base for all CDDE domain errors."""

class WorkflowStateError(CDDEError):
    """Raised when workflow state is missing or invalid for the current operation."""
    def __init__(self, field: str, step: str) -> None: ...
    # Example: WorkflowStateError("spec", "build_dag") → "Required state 'spec' is None at step 'build_dag'"

class DerivationError(CDDEError):
    """Raised when a derivation operation fails."""
    def __init__(self, variable: str, reason: str) -> None: ...

class RepositoryError(CDDEError):
    """Raised when a persistence operation fails."""
    def __init__(self, operation: str, detail: str) -> None: ...
    # Wraps SQLAlchemy IntegrityError, OperationalError, etc.

class DAGError(CDDEError):
    """Raised for DAG structural errors (cycle, missing node, etc.)."""
    def __init__(self, message: str) -> None: ...
```
**Constraints:**
- All inherit from `CDDEError` so callers can catch domain errors generically
- Include structured fields (`variable`, `step`, etc.) not just string messages
- Follow `raise NewError(...) from exc` pattern for chaining
**Reference:** Project rule in `.claude/rules/exception-handling.md`

---

## 2. DerivationRunResult — add to `src/domain/models.py` (MODIFY)

**Purpose:** Atomic result object capturing all outcomes of a single variable derivation run.
**Change:** Add this class after `DAGNode`:
```python
class DerivationRunResult(BaseModel, frozen=True):
    """Atomic result of running coder + QC + verify + debug for one variable."""
    variable: str
    status: DerivationStatus
    coder_code: str | None = None
    coder_approach: str | None = None
    qc_code: str | None = None
    qc_approach: str | None = None
    qc_verdict: QCVerdict | None = None
    approved_code: str | None = None
    debug_analysis: str | None = None
```
**Constraints:**
- Frozen (immutable) — once built, it's a fact
- All fields optional except `variable` and `status` — partial results are valid (e.g., coder succeeded but QC failed)
- No DataFrame or Series fields — only serializable data

---

## 3. Move `workflow_fsm.py` → `src/domain/workflow_fsm.py` (MOVE)

**Rationale:** The FSM defines valid domain state transitions — it's a domain concept, not an orchestration concern.
**Exact change:** Move file, update import from `src.engine.workflow_fsm` → `src.domain.workflow_fsm` everywhere.
**Files that import it (update ALL):**
- `src/engine/orchestrator.py` — `from src.engine.workflow_fsm import WorkflowFSM`
- `tests/unit/test_workflow_fsm.py` — `from src.engine.workflow_fsm import WorkflowFSM`
- `tests/unit/test_orchestrator.py` — `from src.engine.workflow_fsm import WorkflowFSM` (TYPE_CHECKING block)

---

## 4. Move `workflow_models.py` → `src/domain/workflow_models.py` (MOVE)

**Rationale:** `WorkflowState` and `WorkflowResult` are domain state containers.
**Exact change:** Move file, update import from `src.engine.workflow_models` → `src.domain.workflow_models` everywhere.
**Files that import it (update ALL):**
- `src/engine/orchestrator.py` — `from src.engine.workflow_models import WorkflowResult, WorkflowState`
- `src/ui/pages/workflow.py` — `from src.engine.workflow_models import WorkflowResult`
- `tests/unit/test_orchestrator.py` — `from src.engine.workflow_models import WorkflowState`
- `tests/integration/test_workflow.py` — `from src.engine.workflow_models import WorkflowResult`

---

## 5. Move `llm_gateway.py` → `src/config/llm_gateway.py` (MOVE)

**Rationale:** LLM model construction is infrastructure/config, not orchestration logic.
**Exact change:**
- Create `src/config/__init__.py` (empty)
- Move `src/engine/llm_gateway.py` → `src/config/llm_gateway.py`
- Update imports: `src.engine.llm_gateway` → `src.config.llm_gateway`
**Files that import it (update ALL):**
- `src/engine/orchestrator.py` (line 29) — `from src.engine.llm_gateway import create_llm`
- `src/engine/derivation_runner.py` (line 22) — `from src.engine.llm_gateway import create_llm`
- `tests/unit/test_agent_config.py` (lines 103, 118, 129) — `from src.engine.llm_gateway import create_llm`

---

## 6. Move `logging.py` → `src/config/logging.py` (MOVE)

**Rationale:** Logging configuration is infrastructure, not engine logic.
**Exact change:** Move file, update imports.
**Files that import it:**
- `tests/unit/test_logging.py`
- `src/ui/app.py` (if it calls `setup_logging`)

---

## 7. Split `tools.py` → `src/agents/tools/` package (SPLIT)

**Current file:** `src/agents/tools.py` (190 lines) — mixes sandbox config, data inspection, and code execution.

### 7a. `src/agents/tools/__init__.py` (NEW)
**Purpose:** Re-export public API for backward compatibility.
```python
from src.agents.tools.execute_code import execute_code
from src.agents.tools.inspect_data import inspect_data

__all__ = ["execute_code", "inspect_data"]
```

### 7b. `src/agents/tools/sandbox.py` (NEW)
**Purpose:** Sandbox configuration — safe builtins, blocked tokens, namespace builder.
**Move from tools.py:**
- `_SAFE_BUILTINS` constant
- `_BLOCKED_TOKENS` constant
- `_build_sandbox()` function
- `_check_blocked_tokens()` function
**Constraints:** Pure functions, no PydanticAI imports. This is reusable sandbox infrastructure.

### 7c. `src/agents/tools/inspect_data.py` (NEW)
**Purpose:** The `inspect_data` tool — returns schema, nulls, ranges, synthetic sample.
**Move from tools.py:**
- `_build_schema_section()`
- `_build_nulls_section()`
- `_build_ranges_section()`
- `inspect_data()` async function
**Constraints:** Imports `CoderDeps` from `src.agents.deps`, `RunContext` from `pydantic_ai`.

### 7d. `src/agents/tools/execute_code.py` (NEW)
**Purpose:** The `execute_code` tool — runs sandboxed code, returns aggregate summary.
**Move from tools.py:**
- `_format_exec_output()`
- `_summarise_result()`
- `execute_code()` async function
**Imports from:** `src.agents.tools.sandbox` for `_build_sandbox`, `_check_blocked_tokens`
**Constraints:** Imports `CoderDeps` from `src.agents.deps`, `RunContext` from `pydantic_ai`.

### 7e. Delete `src/agents/tools.py` (DELETE)
After split is complete and all imports updated.

**Files that import from tools.py:**
- `src/agents/derivation_coder.py` — `from src.agents.tools import execute_code, inspect_data`
- `src/agents/qc_programmer.py` — `from src.agents.tools import execute_code, inspect_data`
- `tests/unit/test_agent_tools.py` — `from src.agents.tools import ...`

The `__init__.py` re-export ensures these imports continue to work unchanged.

---

## 8. Split `repositories.py` → individual repo files (SPLIT)

**Current file:** `src/persistence/repositories.py` (176 lines) — 4 repo classes with duplicated session handling.

### 8a. `src/persistence/base_repo.py` (NEW)
**Purpose:** Base repository with shared session management and error wrapping.
```python
class BaseRepository:
    """Base for all repositories — provides session access and error wrapping."""
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _flush(self) -> None:
        """Flush session with error wrapping and logging."""
        # Implementation in Phase 10.2 — for now, just delegates to self._session.flush()
        await self._session.flush()
```
**Constraints:** Imports `AsyncSession` from SQLAlchemy. No domain model imports.

### 8b. `src/persistence/pattern_repo.py` (NEW)
**Purpose:** `PatternRepository` — stores/queries validated derivation patterns.
**Move from:** `repositories.py` class `PatternRepository`
**Change:** Inherit from `BaseRepository`, use `self._flush()` instead of `self._session.flush()`.
**Methods (full signatures — copy exactly):**
```python
class PatternRepository(BaseRepository):
    async def store(
        self,
        variable_type: str,
        spec_logic: str,
        approved_code: str,
        study: str,
        approach: str,
    ) -> int: ...

    async def query_by_type(self, variable_type: str, limit: int = 5) -> list[PatternRecord]: ...
```
**Imports:** `from src.domain.models import PatternRecord`, `from src.persistence.orm_models import PatternRow`, `from sqlalchemy import select`, `from datetime import UTC, datetime`
**Reference:** Current implementation in `src/persistence/repositories.py` lines 17-60.

### 8c. `src/persistence/feedback_repo.py` (NEW)
**Purpose:** `FeedbackRepository` — stores/queries human feedback.
**Move from:** `repositories.py` class `FeedbackRepository`
**Change:** Inherit from `BaseRepository`, use `self._flush()` instead of `self._session.flush()`.
**Methods (full signatures):**
```python
class FeedbackRepository(BaseRepository):
    async def store(self, variable: str, feedback: str, action_taken: str, study: str) -> int: ...

    async def query_by_variable(self, variable: str, limit: int = 5) -> list[FeedbackRecord]: ...
```
**Imports:** `from src.domain.models import FeedbackRecord`, `from src.persistence.orm_models import FeedbackRow`, `from sqlalchemy import select`, `from datetime import UTC, datetime`
**Reference:** Current implementation in `src/persistence/repositories.py` lines 63-97.

### 8d. `src/persistence/qc_history_repo.py` (NEW)
**Purpose:** `QCHistoryRepository` — stores QC results, computes stats.
**Move from:** `repositories.py` class `QCHistoryRepository`
**Change:** Inherit from `BaseRepository`, use `self._flush()` instead of `self._session.flush()`.
**Methods (full signatures):**
```python
class QCHistoryRepository(BaseRepository):
    async def store(
        self,
        variable: str,
        verdict: QCVerdict,
        coder_approach: str,
        qc_approach: str,
        study: str,
    ) -> None: ...

    async def get_stats(self, variable: str | None = None) -> QCStats: ...
```
**Imports:** `from src.domain.models import QCStats, QCVerdict`, `from src.persistence.orm_models import QCHistoryRow`, `from sqlalchemy import func, select`, `from datetime import UTC, datetime`
**Reference:** Current implementation in `src/persistence/repositories.py` lines 100-138.

### 8e. `src/persistence/workflow_state_repo.py` (NEW)
**Purpose:** `WorkflowStateRepository` — saves/loads/deletes workflow state.
**Move from:** `repositories.py` class `WorkflowStateRepository`
**Change:** Inherit from `BaseRepository`, use `self._flush()` instead of `self._session.flush()`.
**Methods (full signatures):**
```python
class WorkflowStateRepository(BaseRepository):
    async def save(self, workflow_id: str, state_json: str, fsm_state: str) -> None: ...

    async def load(self, workflow_id: str) -> str | None: ...

    async def delete(self, workflow_id: str) -> None: ...
```
**Imports:** `from src.persistence.orm_models import WorkflowStateRow`, `from sqlalchemy import select`, `from datetime import UTC, datetime`
**Reference:** Current implementation in `src/persistence/repositories.py` lines 141-176.

### 8f. Update `src/persistence/__init__.py` (MODIFY)
**Purpose:** Re-export all repos for backward compatibility.
```python
from src.persistence.base_repo import BaseRepository
from src.persistence.feedback_repo import FeedbackRepository
from src.persistence.pattern_repo import PatternRepository
from src.persistence.qc_history_repo import QCHistoryRepository
from src.persistence.workflow_state_repo import WorkflowStateRepository

__all__ = [
    "BaseRepository",
    "FeedbackRepository",
    "PatternRepository",
    "QCHistoryRepository",
    "WorkflowStateRepository",
]
```

### 8g. Delete `src/persistence/repositories.py` (DELETE)
After split + import updates complete.

**Files that import from repositories.py:**
- `src/factory.py` — `from src.persistence.repositories import PatternRepository, QCHistoryRepository, WorkflowStateRepository`
- `src/engine/orchestrator.py` (TYPE_CHECKING) — same imports
- `tests/unit/test_persistence.py`

---

## 9. Update ALL imports across src/ and tests/ (CRITICAL)

After all moves and splits, update every `import` statement that references the old paths. Grep for:
- `src.engine.workflow_fsm` → `src.domain.workflow_fsm`
- `src.engine.workflow_models` → `src.domain.workflow_models`
- `src.engine.llm_gateway` → `src.config.llm_gateway`
- `src.engine.logging` → `src.config.logging`
- `src.persistence.repositories` → individual repo imports (or use `src.persistence` package)

**Verification:**
1. `uv run ruff check . --fix && uv run ruff format .`
2. `uv run pyright .`
3. `uv run pytest --tb=short -q` — all 148 tests must pass
