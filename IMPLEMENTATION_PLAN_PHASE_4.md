# Phase 4 — Persistence + Audit + Integration Test

**Dependencies:** Phase 1 + 2 + 3 (everything)
**Agent:** `python-fastapi`
**Estimated files:** 11 (was 8 — added `database.py`, `repositories.py`, `orm_models.py`)

This phase adds persistence (SQLAlchemy-backed repository layer), the audit trail, and the end-to-end integration test. The persistence layer uses SQLAlchemy with async sessions, enabling zero-code-change swapping between SQLite (local dev) and PostgreSQL (Docker/production).

**New dependency:** `sqlalchemy[asyncio]>=2.0,<3` + `aiosqlite>=0.21,<1` (async SQLite driver)

---

## 4.1 Persistence Layer (SQLAlchemy)

### `src/persistence/__init__.py` (NEW)

Empty file.

### `src/persistence/database.py` (NEW)

**Purpose:** Database engine + session factory. Single configuration point for all database access.

**Public API:**

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.persistence.orm_models import Base

async def init_db(database_url: str = "sqlite+aiosqlite:///cdde.db") -> async_sessionmaker[AsyncSession]:
    """Create engine + session factory. Creates tables if needed.

    Usage:
    - Local dev:  init_db("sqlite+aiosqlite:///cdde.db")
    - Docker:     init_db("postgresql+asyncpg://user:pass@db:5432/cdde")
    - Tests:      init_db("sqlite+aiosqlite:///:memory:")

    Returns async_sessionmaker for dependency injection.

    IMPORTANT — async table creation pattern:
        engine = create_async_engine(database_url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return async_sessionmaker(engine, expire_on_commit=False)
    """

async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session. For use with FastAPI Depends() or manual context manager."""
```

**Constraints:**
- Engine URL from environment variable `DATABASE_URL` with SQLite default
- `create_async_engine(url, echo=False)` — echo only in DEBUG
- Tables created via `await conn.run_sync(Base.metadata.create_all)` — NOT sync `create_all()` which fails on async engines
- `expire_on_commit=False` on sessionmaker (prevents lazy-load errors after commit in async)
- No global engine or session — always injected

### `src/persistence/orm_models.py` (NEW)

**Purpose:** SQLAlchemy ORM models for persistent tables. Separate from domain models (ORM is infrastructure).

**Tables:**

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, Text, DateTime
from datetime import datetime

class Base(DeclarativeBase):
    pass

class PatternRow(Base):
    __tablename__ = "patterns"
    id: Mapped[int] = mapped_column(primary_key=True)
    variable_type: Mapped[str] = mapped_column(String(100), index=True)
    spec_logic: Mapped[str] = mapped_column(Text)
    approved_code: Mapped[str] = mapped_column(Text)
    study: Mapped[str] = mapped_column(String(100))
    approach: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class FeedbackRow(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    variable: Mapped[str] = mapped_column(String(100), index=True)
    feedback: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(String(200))
    study: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class QCHistoryRow(Base):
    __tablename__ = "qc_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    variable: Mapped[str] = mapped_column(String(100), index=True)
    verdict: Mapped[str] = mapped_column(String(50))  # stores QCVerdict enum values: "match", "mismatch", "insufficient_independence"
    coder_approach: Mapped[str] = mapped_column(String(200))
    qc_approach: Mapped[str] = mapped_column(String(200))
    study: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class WorkflowStateRow(Base):
    __tablename__ = "workflow_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    state_json: Mapped[str] = mapped_column(Text)  # Serialized WorkflowState
    fsm_state: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

**Constraints:**
- SQLAlchemy 2.0 style: `Mapped[]`, `mapped_column()`, `DeclarativeBase`
- Indexes on columns used in WHERE clauses
- No business logic in ORM models
- ORM models are infrastructure — domain models remain in `src/domain/models.py`

### `src/persistence/repositories.py` (NEW)

**Purpose:** Repository classes that wrap SQLAlchemy queries. Services and orchestrator depend on these interfaces, never on sessions directly.

**Public classes:**

```python
from sqlalchemy.ext.asyncio import AsyncSession

class PatternRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def store(
        self, variable_type: str, spec_logic: str, approved_code: str, study: str, approach: str,
    ) -> int: ...

    async def query_by_type(self, variable_type: str, limit: int = 5) -> list[PatternRecord]: ...

class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def store(self, variable: str, feedback: str, action_taken: str, study: str) -> int: ...

    async def query_by_variable(self, variable: str, limit: int = 5) -> list[FeedbackRecord]: ...

class QCHistoryRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def store(
        self, variable: str, verdict: str, coder_approach: str, qc_approach: str, study: str,
    ) -> None: ...

    async def get_stats(self, variable: str | None = None) -> QCStats: ...

class WorkflowStateRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def save(self, workflow_id: str, state_json: str, fsm_state: str) -> None: ...

    async def load(self, workflow_id: str) -> str | None: ...

    async def delete(self, workflow_id: str) -> None: ...
```

**Constraints:**
- Repositories return domain models (Pydantic), never ORM rows
- All queries use `select()` (SQLAlchemy 2.0 style), never `session.query()`
- All queries parameterized (no SQL injection)
- Repositories accept `AsyncSession` via constructor — injected by caller
- All methods are async
- Tests use `sqlite+aiosqlite:///:memory:` — same code path as production

---

## 4.1b Domain Model Additions

### `src/domain/models.py` (MODIFY)

**Purpose:** Add persistence-related domain models. These are domain models (not ORM), used as return types by repositories.

**Add these 3 classes at the end of the file, after `AuditRecord`:**

```python
class PatternRecord(BaseModel, frozen=True):
    """A validated derivation pattern stored for cross-run reuse."""
    id: int
    variable_type: str
    spec_logic: str
    approved_code: str
    study: str
    approach: str
    created_at: str  # ISO 8601

class FeedbackRecord(BaseModel, frozen=True):
    """Human feedback on a derivation, stored for learning."""
    id: int
    variable: str
    feedback: str
    action_taken: str
    study: str
    created_at: str  # ISO 8601

class QCStats(BaseModel, frozen=True):
    """Aggregate QC statistics from historical runs."""
    total: int
    matches: int
    mismatches: int
    match_rate: float
```

**Constraints:**
- These live in `src/domain/models.py`, NOT in `src/persistence/` — they are domain models used by repositories as return types and by the orchestrator
- All `frozen=True` (immutable)
- `created_at` is `str` (ISO 8601) not `datetime` — matches AuditRecord pattern

---

## 4.2 Audit Trail

### `src/audit/__init__.py` (NEW)

Empty file.

### `src/audit/trail.py` (NEW)

**Purpose:** Append-only audit trail management. Records every action in the workflow. This is a **domain service** — no database dependency. The orchestrator collects records here and persists them via the repository layer.

**Public class:**

```python
class AuditTrail:
    """Append-only audit trail for a workflow run."""

    def __init__(self, workflow_id: str) -> None:
        """Initialize empty trail."""

    @property
    def records(self) -> list[AuditRecord]:
        """All records in chronological order (read-only copy)."""

    def record(
        self,
        variable: str,
        action: str,
        agent: str,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> AuditRecord:
        """Append a new audit record. Returns the created record."""

    def get_variable_history(self, variable: str) -> list[AuditRecord]:
        """All records for a specific variable."""

    def to_dict(self) -> list[dict[str, object]]:
        """Export trail as list of dicts (for JSON serialization)."""

    def to_json(self, path: Path) -> None:
        """Export trail to JSON file."""

    def summary(self) -> dict[str, int]:
        """Aggregate stats: actions by type, by agent."""
```

**Constraints:**
- Append-only — no `delete()` or `update()` methods
- `record()` auto-generates timestamp (UTC ISO 8601)
- Thread-safe: use a list with no deletion
- No dependencies on LLM, agent framework, or database

---

## 4.3 Layer Architecture (Separation of Concerns)

The persistence layer follows strict SoC:

```
Orchestrator (engine/)
    │
    ├── uses AuditTrail (audit/) — in-memory, domain service
    │
    └── depends on Repositories (persistence/repositories.py) — injected
            │
            └── depends on AsyncSession (persistence/database.py) — injected
                    │
                    └── maps to ORM models (persistence/orm_models.py)
                            │
                            └── backed by SQLAlchemy engine (SQLite or PostgreSQL)
```

| Layer | File | Depends on | Returns |
|-------|------|------------|---------|
| **Orchestrator** | `engine/orchestrator.py` | Repositories (via constructor DI) | `WorkflowResult` (domain) |
| **Repositories** | `persistence/repositories.py` | `AsyncSession`, ORM models | Domain models (`PatternRecord`, etc.) |
| **ORM Models** | `persistence/orm_models.py` | SQLAlchemy only | — |
| **Database** | `persistence/database.py` | SQLAlchemy engine | `async_sessionmaker` |
| **Audit Trail** | `audit/trail.py` | Domain models only | `AuditRecord` list |

**Rules:**
- Orchestrator NEVER imports `AsyncSession`, `orm_models`, or `database.py`
- Orchestrator receives repositories via constructor injection
- Repositories return Pydantic domain models, never ORM rows
- AuditTrail is pure domain — no DB dependency (JSON export is file I/O, not DB)

### `src/engine/orchestrator.py` (MODIFY)

**Updated constructor signature:**

```python
from src.persistence.repositories import (
    PatternRepository,
    QCHistoryRepository,
    WorkflowStateRepository,
)
from src.audit.trail import AuditTrail

class DerivationOrchestrator:
    def __init__(
        self,
        spec_path: str | Path,
        llm_base_url: str = "http://localhost:8650/v1",
        pattern_repo: PatternRepository | None = None,
        qc_repo: QCHistoryRepository | None = None,
        state_repo: WorkflowStateRepository | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._spec_path = Path(spec_path)
        self._llm_base_url = llm_base_url
        self._fsm = WorkflowFSM(workflow_id=uuid4().hex[:8])
        self._state = WorkflowState(workflow_id=self._fsm.workflow_id)
        self._pattern_repo = pattern_repo
        self._qc_repo = qc_repo
        self._state_repo = state_repo
        self._output_dir = output_dir
        self._audit_trail = AuditTrail(self._fsm.workflow_id)
```

**IMPORTANT — import-linter exception:** The orchestrator imports repository TYPE NAMES for type annotations. This does NOT violate engine-no-persistence because these are constructor parameter types, not direct usage. However, to keep it fully clean, consider using `TYPE_CHECKING`:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.persistence.repositories import (
        PatternRepository,
        QCHistoryRepository,
        WorkflowStateRepository,
    )
```

This way the import is type-checking only — no runtime dependency on persistence. The actual repo objects are injected by the caller.

**Changes to existing methods:**
1. **`run()`:** After loading source data, merge FSM audit_records into `self._audit_trail`. On completion, export audit trail if `output_dir` is set.
2. **`_run_derivation()` (in `derivation_runner.py`):** Accept optional `pattern_repo` and `qc_repo`. Before running coder, query patterns: `if pattern_repo: patterns = await pattern_repo.query_by_type(rule.variable)`. After QC pass, store: `if pattern_repo: await pattern_repo.store(...)`. After comparison, store QC result: `if qc_repo: await qc_repo.store(...)`.
3. **FSM `after_transition` callback:** If `state_repo` is set, persist workflow state after each transition.
4. **`run()` final step:** `if self._output_dir: self._audit_trail.to_json(self._output_dir / "audit_trail.json")`

**Constraints:**
- All repositories are optional (`None` = skip persistence). Unit tests run without DB.
- Orchestrator uses `TYPE_CHECKING` import for repo types — no runtime dependency on persistence module
- `WorkflowResult.audit_records` populated from `self._audit_trail.records`
- `FeedbackRepository` is NOT wired in the orchestrator — feedback comes from HITL UI (Phase 5+)

### `tests/unit/test_persistence.py` (NEW)

**Tests (all async, use `sqlite+aiosqlite:///:memory:`):**
- `test_pattern_repo_store_and_query` — store pattern, query by type, verify fields
- `test_pattern_repo_query_empty_returns_empty_list` — no data → `[]`
- `test_pattern_repo_query_respects_limit` — store 10, query limit=3 → 3 results
- `test_feedback_repo_store_and_query` — store feedback, query by variable
- `test_qc_repo_store_and_get_stats` — store results, verify match_rate
- `test_qc_repo_stats_empty` — no data → total=0, match_rate=0.0
- `test_workflow_state_repo_save_and_load` — save JSON, load back, verify
- `test_workflow_state_repo_load_nonexistent_returns_none` — missing workflow → None
- `test_workflow_state_repo_delete` — save then delete, verify gone
- `test_init_db_creates_tables` — init_db with memory DB, verify tables exist

**Fixtures:**
```python
@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    session_factory = await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory() as session:
        yield session
```

### `tests/unit/test_audit.py` (NEW)

**Tests:**
- `test_audit_trail_append_only` — records grow, no delete method exists
- `test_audit_trail_record_generates_timestamp` — verify ISO format
- `test_audit_trail_get_variable_history` — filter by variable name
- `test_audit_trail_to_json_creates_file` — export to tmp_path, verify valid JSON
- `test_audit_trail_summary_counts` — verify action/agent aggregation

---

## 4.4 Integration Test

### `tests/integration/__init__.py` (NEW)

Empty file.

### `tests/integration/test_workflow.py` (NEW)

**Purpose:** End-to-end test that runs the full orchestrator with `simple_mock.yaml`, with persistence and audit wired in. Uses mocked LLM responses.

**IMPORTANT:** This test validates the FULL pipeline but does NOT require a running AgentLens server. Instead, it mocks the LLM calls at the PydanticAI level using `pydantic_ai.models.test.TestModel` or by mocking the HTTP calls.

**Tests:**

```python
@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite session for integration tests."""
    session_factory = await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory() as session:
        yield session

@pytest.mark.asyncio
async def test_full_workflow_simple_mock(
    sample_spec_path: Path,
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    """End-to-end: parse spec → build DAG → run agents → verify → audit.

    Uses TestModel to provide canned LLM responses.
    Repositories injected with in-memory DB session.

    Assertions:
    - Workflow completes with status "completed"
    - All 4 variables derived (AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY, RISK_SCORE)
    - DAG has 3 layers
    - All QC verdicts are "match"
    - Audit trail has records for each step
    - Patterns stored in DB after approval
    - No errors in workflow result
    """

@pytest.mark.asyncio
async def test_workflow_qc_mismatch_triggers_debugger(
    sample_spec_path: Path,
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    """Test that QC mismatch triggers Debugger agent.

    Mock QC to return wrong code for one variable.
    Verify:
    - Debugger is called
    - DAG node status shows QC_MISMATCH
    - Audit trail records the mismatch and debug attempt
    - QC history stored in DB with mismatch verdict
    """

@pytest.mark.asyncio
async def test_workflow_dag_order_respected(
    sample_spec_path: Path,
    tmp_path: Path,
) -> None:
    """Verify derivations execute in correct DAG order.

    Track the order of agent calls via audit trail.
    AGE_GROUP and TREATMENT_DURATION must complete before IS_ELDERLY.
    IS_ELDERLY must complete before RISK_SCORE.
    """
```

**Mocking strategy — use `pydantic_ai.models.test.TestModel`:**

```python
from pydantic_ai.models.test import TestModel

# TestModel API (verified against installed pydantic-ai):
# TestModel(custom_output_args=<dict matching output type fields>)
# When agent.run() is called with this model, it returns the canned output directly.
# Use agent.override(model=TestModel(...)) to inject.
```

**Canned outputs for each agent:**

```python
# Spec Interpreter — return the rules from simple_mock.yaml
spec_test_model = TestModel(custom_output_args={
    "rules": [
        {"variable": "AGE_GROUP", "source_columns": ["age"], "logic": "...", "output_type": "str"},
        # ... all 4 rules matching simple_mock.yaml
    ],
    "ambiguities": [],
    "summary": "Parsed 4 derivation rules",
})

# Coder — return correct pandas code per variable
coder_age_group = TestModel(custom_output_args={
    "variable_name": "AGE_GROUP",
    "python_code": "pd.cut(df['age'], bins=[0,18,65,200], labels=['minor','adult','senior'], right=False)",
    "approach": "pd.cut with bins",
    "null_handling": "NaN propagated by pd.cut",
})

# QC — return alternative correct code (different approach)
qc_age_group = TestModel(custom_output_args={
    "variable_name": "AGE_GROUP",
    "python_code": "np.select([df['age']<18, df['age']<65, df['age']>=65], ['minor','adult','senior'], default=None)",
    "approach": "np.select with conditions",
    "null_handling": "default=None for NaN",
})

# Auditor — summary
auditor_test_model = TestModel(custom_output_args={
    "study": "simple_mock",
    "total_derivations": 4,
    "auto_approved": 4,
    "qc_mismatches": 0,
    "human_interventions": 0,
    "summary": "All derivations passed QC",
    "recommendations": [],
})
```

**Integration test fixtures:**

```python
@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite session for integration tests."""
    session_factory = await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory() as session:
        yield session

@pytest.fixture
def repos(db_session: AsyncSession) -> dict[str, Any]:
    """Create all repositories from a single session."""
    return {
        "pattern_repo": PatternRepository(db_session),
        "qc_repo": QCHistoryRepository(db_session),
        "state_repo": WorkflowStateRepository(db_session),
    }
```

**Constraints:**
- Tests MUST be deterministic — no real LLM calls, use `TestModel` exclusively
- Tests MUST run in CI without AgentLens server
- Use `tmp_path` for all file operations (audit export)
- Use `sqlite+aiosqlite:///:memory:` for DB tests (same code path as production)
- Assert specific audit trail contents, not just "trail is non-empty"
- Use `agent.override(model=TestModel(...))` to inject canned outputs per agent call

**Post-implementation step:** Uncomment Phase 4 contracts in `.importlinter` and verify `uv run lint-imports` passes.
