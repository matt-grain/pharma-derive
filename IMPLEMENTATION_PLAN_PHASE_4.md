# Phase 4 — Memory + Audit + Integration Test

**Dependencies:** Phase 1 + 2 + 3 (everything)
**Agent:** `python-fastapi`
**Estimated files:** 8

This phase adds memory (short-term + long-term), the audit trail, and the end-to-end integration test that validates the full pipeline via AgentLens mailbox.

---

## 4.1 Memory Layer

### `src/memory/__init__.py` (NEW)

Empty file.

### `src/memory/short_term.py` (NEW)

**Purpose:** Per-run workflow state persistence. Enables resuming interrupted workflows.

**Public class:**

```python
class ShortTermMemory:
    """Per-run state — JSON file backed. Cleared after workflow completes."""

    def __init__(self, storage_dir: Path, workflow_id: str) -> None:
        """Initialize. Creates storage_dir if needed."""

    def save_state(self, state: WorkflowState) -> None:
        """Persist current workflow state to JSON."""

    def load_state(self) -> WorkflowState | None:
        """Load state if exists, None otherwise."""

    def save_intermediate(self, variable: str, result_series_json: str) -> None:
        """Save intermediate derivation result (serialized Series)."""

    def load_intermediate(self, variable: str) -> str | None:
        """Load intermediate result for a variable if exists."""

    def clear(self) -> None:
        """Delete all state files for this run."""
```

**Implementation details:**
- Storage: `{storage_dir}/{workflow_id}/state.json` and `{storage_dir}/{workflow_id}/{variable}.json`
- Use Pydantic's `.model_dump_json()` / `.model_validate_json()` for serialization
- `WorkflowState` has a `dag` field that isn't directly serializable — serialize DAG nodes as list, reconstruct on load

**Constraints:**
- File operations use `pathlib.Path` — no raw `open()` with string paths
- Thread-safe: use file locking or atomic writes (write to temp file, rename)

### `src/memory/long_term.py` (NEW)

**Purpose:** Cross-run knowledge base. Stores validated patterns and feedback for reuse.

**Public class:**

```python
class LongTermMemory:
    """Cross-run knowledge — SQLite backed. Persists across workflows."""

    def __init__(self, db_path: Path) -> None:
        """Initialize. Creates DB and tables if needed."""

    def store_pattern(
        self,
        variable_type: str,      # e.g., "AGE_GROUP", "TREATMENT_DURATION"
        spec_logic: str,         # The derivation logic from the spec
        approved_code: str,      # The code that passed QC
        study: str,
        approach: str,
    ) -> int:
        """Store a validated derivation pattern. Returns pattern ID."""

    def query_patterns(
        self,
        variable_type: str,
        limit: int = 5,
    ) -> list[PatternRecord]:
        """Query patterns by variable type. Returns most recent first."""

    def store_feedback(
        self,
        variable: str,
        feedback: str,
        action_taken: str,
        study: str,
    ) -> int:
        """Store human feedback for a derivation."""

    def query_feedback(
        self,
        variable: str,
        limit: int = 5,
    ) -> list[FeedbackRecord]:
        """Query feedback by variable name."""

    def store_qc_result(
        self,
        variable: str,
        verdict: str,
        coder_approach: str,
        qc_approach: str,
        study: str,
    ) -> None:
        """Store QC comparison result for historical analysis."""

    def get_qc_stats(self, variable: str | None = None) -> QCStats:
        """Aggregate QC stats — match rate, common mismatch patterns."""
```

**Supporting models (define in this file):**

```python
class PatternRecord(BaseModel, frozen=True):
    id: int
    variable_type: str
    spec_logic: str
    approved_code: str
    study: str
    approach: str
    created_at: str

class FeedbackRecord(BaseModel, frozen=True):
    id: int
    variable: str
    feedback: str
    action_taken: str
    study: str
    created_at: str

class QCStats(BaseModel, frozen=True):
    total: int
    matches: int
    mismatches: int
    match_rate: float
```

**Implementation details:**
- SQLite via `sqlite3` (stdlib) — no ORM, raw SQL
- Three tables: `patterns`, `feedback`, `qc_history`
- Schema created in `__init__` via `CREATE TABLE IF NOT EXISTS`
- All timestamps are ISO 8601 UTC

**Constraints:**
- No `Any` types
- All queries parameterized (no SQL injection)
- DB path configurable — tests use `:memory:`, production uses file path
- Repository pattern: if we switch to PostgreSQL later, only this file changes

---

## 4.2 Audit Trail

### `src/audit/__init__.py` (NEW)

Empty file.

### `src/audit/trail.py` (NEW)

**Purpose:** Append-only audit trail management. Records every action in the workflow.

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
- No dependencies on LLM or agent framework

---

## 4.3 Wire Memory + Audit into Orchestrator

### `src/engine/orchestrator.py` (MODIFY)

**Changes:**
1. **Add `ShortTermMemory` to `__init__`:** Accept optional `state_dir: Path` parameter. Create `ShortTermMemory(state_dir, workflow_id)`. Save state after each FSM transition.
2. **Add `LongTermMemory` to `__init__`:** Accept optional `db_path: Path` parameter. Create `LongTermMemory(db_path)`.
3. **Add `AuditTrail` to `__init__`:** Create `AuditTrail(workflow_id)`. Replace `state.audit_records.append(...)` with `self.audit_trail.record(...)`.
4. **Query patterns before derivation:** In `_run_derivation()`, call `long_term.query_patterns(rule.variable)`. If patterns found, include them in the agent prompt as "Reference: previously approved pattern for this variable type: {code}".
5. **Store patterns after approval:** After a derivation passes QC, call `long_term.store_pattern(variable, logic, approved_code, study, approach)`.
6. **Store QC results:** After comparison, call `long_term.store_qc_result(variable, verdict, coder_approach, qc_approach, study)`.
7. **Export audit on completion:** In the final step, call `self.audit_trail.to_json(output_dir / "audit_trail.json")`.

**Constraints:**
- Memory and audit are optional — if `state_dir` or `db_path` is None, skip persistence (allows running without filesystem for unit tests)
- AuditTrail records replace the inline `state.audit_records` list
- `WorkflowResult.audit_records` populated from `self.audit_trail.records`

### `tests/unit/test_memory.py` (NEW)

**Tests:**
- `test_short_term_save_and_load_state` — save WorkflowState, load it back, verify fields match
- `test_short_term_save_intermediate` — save a variable result, load it back
- `test_short_term_clear_removes_files` — clear removes all state files
- `test_short_term_load_nonexistent_returns_none` — no file → None
- `test_long_term_store_and_query_pattern` — store pattern, query by variable type, verify returned
- `test_long_term_query_patterns_empty` — query non-existent type → empty list
- `test_long_term_store_and_query_feedback` — store feedback, query by variable
- `test_long_term_store_qc_result_and_stats` — store results, get_qc_stats returns correct rates
- `test_long_term_uses_memory_db_for_tests` — verify `:memory:` works

**Fixtures:** Use `tmp_path` for ShortTermMemory, `:memory:` path for LongTermMemory.

### `tests/unit/test_audit.py` (NEW)

**Tests:**
- `test_audit_trail_append_only` — records grow, no delete method
- `test_audit_trail_record_generates_timestamp` — verify ISO format
- `test_audit_trail_get_variable_history` — filter by variable name
- `test_audit_trail_to_json_creates_file` — export to tmp_path, verify valid JSON
- `test_audit_trail_summary_counts` — verify action/agent aggregation

---

## 4.4 Integration Test

### `tests/integration/__init__.py` (NEW)

Empty file.

### `tests/integration/test_workflow.py` (NEW)

**Purpose:** End-to-end test that runs the full orchestrator with `simple_mock.yaml`, with memory and audit wired in. Uses mocked LLM responses.

**IMPORTANT:** This test validates the FULL pipeline but does NOT require a running AgentLens server. Instead, it mocks the LLM calls at the PydanticAI level using `pydantic_ai.models.test.TestModel` or by mocking the HTTP calls.

**Tests:**

```python
@pytest.mark.asyncio
async def test_full_workflow_simple_mock(
    sample_spec_path: Path,
    tmp_path: Path,
) -> None:
    """End-to-end: parse spec → build DAG → run agents → verify → audit.

    Uses TestModel to provide canned LLM responses:
    - Spec Interpreter: returns parsed rules matching simple_mock.yaml
    - Coder: returns correct pandas code for each variable
    - QC: returns alternative pandas code for each variable
    - Auditor: returns summary

    Assertions:
    - Workflow completes with status "completed"
    - All 4 variables derived (AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY, RISK_SCORE)
    - DAG has 3 layers
    - All QC verdicts are "match"
    - Audit trail has records for each step
    - No errors in workflow result
    """

@pytest.mark.asyncio
async def test_workflow_qc_mismatch_triggers_debugger(
    sample_spec_path: Path,
    tmp_path: Path,
) -> None:
    """Test that QC mismatch triggers Debugger agent.

    Mock QC to return wrong code for one variable.
    Verify:
    - Debugger is called
    - DAG node status shows QC_MISMATCH
    - Audit trail records the mismatch and debug attempt
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

**Mocking strategy:**
- Use `pydantic_ai.models.test.TestModel` if available, otherwise mock `httpx.AsyncClient` at the transport level
- Provide canned responses that match the expected structured output schemas
- Coder responses: correct pandas code (tested in unit tests)
- QC responses: alternative correct pandas code

**Constraints:**
- Tests MUST be deterministic — no real LLM calls
- Tests MUST run in CI without AgentLens server
- Use `tmp_path` for all file operations (state, audit export)
- Assert specific audit trail contents, not just "trail is non-empty"
