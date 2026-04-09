# Phase 3 — Orchestration Engine + Verification

**Dependencies:** Phase 1 (domain models, DAG) + Phase 2 (agents, LLM gateway)
**Agent:** `python-fastapi`
**Estimated files:** 10 (was 8 — added `workflow_fsm.py` + `test_workflow_fsm.py`)

This phase implements the orchestration layer — the workflow FSM, DAG-ordered executor, and QC comparator. This is where PydanticAI agents are composed into the clinical derivation pipeline using standard Python async patterns.

**FSM library:** `python-statemachine` v3.0 — provides formal state machine definition with transition callbacks (for automatic logging + audit trail), guards, and `.graph()` export for presentation diagrams. Chosen over hand-rolled dict because clinical workflow transitions require audit logging on every state change — callbacks handle this declaratively instead of manually.

---

## 3.1 Workflow State Machine

### `src/engine/workflow_fsm.py` (NEW)

**Purpose:** Formal FSM definition using `python-statemachine`. Separated from `orchestrator.py` to keep the FSM definition pure and independently testable.

**Implementation:**

```python
from datetime import datetime, timezone
from statemachine import StateMachine, State
from statemachine.exceptions import TransitionNotAllowed  # raised on invalid transitions
from loguru import logger
from src.domain.models import AuditRecord

class WorkflowFSM(StateMachine):
    """Clinical derivation workflow state machine.

    States follow the WorkflowStep StrEnum values from domain/models.py.
    Transition callbacks handle logging and audit trail automatically.
    """

    # --- States ---
    created = State(initial=True)
    spec_review = State()
    dag_built = State()
    deriving = State()
    verifying = State()
    debugging = State()
    review = State()
    auditing = State()
    completed = State(final=True)
    failed = State(final=True)

    # --- Transitions ---
    # Named transitions for each valid edge in the FSM
    start_spec_review = created.to(spec_review)
    finish_spec_review = spec_review.to(dag_built)
    start_deriving = dag_built.to(deriving)
    start_verifying = deriving.to(verifying)
    next_variable = verifying.to(deriving)      # loop back for next variable
    start_debugging = verifying.to(debugging)
    finish_review_from_verify = verifying.to(review)  # all variables done
    retry_from_debug = debugging.to(verifying)
    finish_review_from_debug = debugging.to(review)   # escalate to human
    start_auditing = review.to(auditing)
    finish = auditing.to(completed)

    # Failure transitions — any non-terminal state can fail
    fail_from_created = created.to(failed)
    fail_from_spec_review = spec_review.to(failed)
    fail_from_dag_built = dag_built.to(failed)
    fail_from_deriving = deriving.to(failed)
    fail_from_verifying = verifying.to(failed)
    fail_from_debugging = debugging.to(failed)
    fail_from_review = review.to(failed)
    fail_from_auditing = auditing.to(failed)

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        self.audit_records: list[AuditRecord] = []
        super().__init__()

    def after_transition(self, source: State, target: State, event: str) -> None:
        """Called after every transition — logs and creates audit record.

        NOTE: python-statemachine v3.0 API:
        - `after_transition(self, source, target, event)` — called after any transition
        - `source` / `target` are State objects, use `.id` for string name
        - `event` is the transition method name (e.g., "start_spec_review")
        """
        logger.info(
            "Workflow {wf_id}: {source} → {target} (via {event})",
            wf_id=self.workflow_id, source=source.id, target=target.id, event=event,
        )
        self.audit_records.append(
            AuditRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                workflow_id=self.workflow_id,
                variable="",
                action=f"state_transition:{target.id}",
                agent="orchestrator",
                details={"event": event, "from": source.id},
            )
        )

    def fail(self, error: str = "") -> None:
        """Convenience: transition to failed from any non-terminal state.
        Selects the correct fail_from_* transition based on current state.
        """
        fail_transition_name = f"fail_from_{self.current_state_value}"
        getattr(self, fail_transition_name)()
```

**Constraints:**
- States mirror `WorkflowStep` StrEnum values exactly (same names, lowercase)
- `after_transition` callback handles logging + audit automatically — orchestrator doesn't need manual logging on transitions
- `fail()` convenience method maps current state to the correct `fail_from_*` transition
- FSM is independently testable — no agent or DataFrame dependencies

**python-statemachine v3.0 API reference (verified against installed version):**
- `State(initial=True)`, `State(final=True)`, `state_a.to(state_b)`
- `fsm.current_state_value` → string id (e.g., `"created"`). NOTE: `current_state` property is DEPRECATED — use `current_state_value` instead
- Invalid transitions raise `statemachine.exceptions.TransitionNotAllowed` (NOT `ValueError`)
- Callbacks: `after_transition(self, source, target, event)` — source/target are `State` objects, event is transition method name
- Per-state callbacks: `on_enter_<state_name>(self)`, `on_exit_<state_name>(self)` — named after the state
- `on_enter_state(self, state, target)` is the generic callback (called on initial state too) — `state == target` (both refer to the state being entered)

### `src/engine/orchestrator.py` (NEW)

**Purpose:** Top-level workflow controller. Uses `WorkflowFSM` for state management and dispatches agents.

**Public class:**

```python
class DerivationOrchestrator:
    """Orchestrates the full derivation workflow."""

    def __init__(
        self,
        spec_path: str | Path,
        llm_base_url: str = "http://localhost:8650/v1",
    ) -> None:
        """Initialize with spec path and LLM config.
        Creates WorkflowFSM and WorkflowState."""
        self._fsm = WorkflowFSM(workflow_id=uuid4().hex[:8])
        self._state = WorkflowState(workflow_id=self._fsm.workflow_id)

    @property
    def state(self) -> WorkflowState:
        """Current workflow state (read-only view)."""

    @property
    def fsm(self) -> WorkflowFSM:
        """Access to the FSM for state queries."""

    async def run(self) -> WorkflowResult:
        """Execute the full workflow end-to-end.
        Returns WorkflowResult with derived DataFrame + audit trail.

        Steps:
        1. Parse spec → TransformationSpec
        2. Load source data → DataFrame
        3. Generate synthetic reference → DataFrame
        4. Build DAG from spec + source columns
        5. Run Spec Interpreter agent (→ validated rules + ambiguities)
        6. For each DAG layer:
           a. For each variable in layer (fan-out via asyncio.gather):
              - Run Coder + QC in parallel (asyncio.gather)
              - Compare outputs (comparator)
              - If mismatch: run Debugger (up to 2 attempts)
              - Update DAG node with results
        7. Run Auditor agent → AuditSummary
        8. Return results
        """

    async def _run_spec_interpretation(self) -> SpecInterpretation:
        """Run Spec Interpreter agent."""

    async def _run_derivation(self, variable: str) -> None:
        """Run Coder + QC + Compare for a single variable."""

    async def _run_dag_layer(self, layer: list[str]) -> None:
        """Fan-out: run all variables in a layer concurrently."""

    async def _run_debugger(self, variable: str) -> DebugAnalysis:
        """Run Debugger agent on a QC mismatch."""

    async def _run_auditor(self) -> AuditSummary:
        """Run Auditor agent on completed DAG."""
```

**Supporting models (define in this file):**

```python
class WorkflowStatus(StrEnum):
    """Final status of a workflow run."""
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class WorkflowState:
    """Current state of the workflow.
    NOTE: dataclass, NOT BaseModel — because DerivationDAG wraps networkx
    which is not Pydantic-serializable. For persistence, use ShortTermMemory
    which serializes individual fields.
    """
    workflow_id: str
    spec: TransformationSpec | None = None
    dag: DerivationDAG | None = None
    derived_df: pd.DataFrame | None = None   # DataFrame with derived columns added
    synthetic_csv: str = ""                   # Generated synthetic reference for agent prompts
    current_variable: str | None = None
    errors: list[str] = field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None

class WorkflowResult(BaseModel, frozen=True):
    """Final output of a workflow run."""
    workflow_id: str
    study: str
    status: WorkflowStatus               # StrEnum, not raw str
    derived_variables: list[str]
    qc_summary: dict[str, str]           # variable → verdict
    audit_records: list[AuditRecord]
    audit_summary: AuditSummary | None = None
    errors: list[str]
    duration_seconds: float
```

**Constraints:**
- State transitions go through `self._fsm` — NEVER assign `_state.step` directly
- `WorkflowState` no longer has `step` or `audit_records` fields — those live on the FSM
- `self._fsm.current_state_value` gives current step name as string (matches WorkflowStep values). NOTE: `current_state` is DEPRECATED in v3.0
- `self._fsm.audit_records` holds the audit trail (populated by FSM callbacks)
- Each step uses named transitions: `self._fsm.start_spec_review()`, `self._fsm.finish_spec_review()`, etc.
- Errors call `self._fsm.fail(error=msg)` which auto-routes to the correct `fail_from_*` transition
- `_run_derivation` uses `asyncio.gather` for Coder + QC (as validated in prototype)
- `_run_dag_layer` uses `asyncio.gather` for all variables in the layer
- Agent `model` is set via `agent.override(model=create_llm(llm_base_url))`
- NO HITL gates in this phase — auto-approve everything (HITL added in UI phase later)
- **Synthetic data wiring:** In `run()`, after loading source data, call `generate_synthetic(df)` from `spec_parser.py` and store as `state.synthetic_csv = synthetic_df.to_csv(index=False)`. Pass this to `CoderDeps.synthetic_csv` in `_run_derivation()`.
- **Derived columns accumulate:** `state.derived_df` starts as a copy of source df. After each approved derivation, the new column is added to `derived_df`. The next derivation's `CoderDeps.df` is `state.derived_df` (with previously derived columns available).

---

### `src/engine/logging.py` (NEW)

**Purpose:** Configure loguru for the orchestration engine.

**Public function:**

```python
from loguru import logger

def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure loguru for the orchestration engine.

    Removes default stderr handler, adds:
    - Console handler with colored output at `level`
    - File handler (if log_file provided) at DEBUG level for full trace

    Log format: "{time:HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}"
    """
```

**Constraints:**
- Called once at orchestrator init
- Uses `logger.remove()` to clear defaults, then `logger.add()` for each sink
- No global side effects on import — only on explicit `setup_logging()` call

---

## 3.2 DAG Executor

### `src/domain/executor.py` (NEW)

**Purpose:** Executes generated derivation code safely on a DataFrame. Lives in `domain/` because code execution is pure domain logic (no framework deps) and `verification/comparator.py` depends on it (verification depends on domain only).

**Public functions:**

```python
def execute_derivation(
    df: pd.DataFrame,
    code: str,
    available_columns: list[str],
) -> ExecutionResult:
    """Execute a derivation code string on the DataFrame.

    The code is evaluated in a restricted namespace:
    - `df` (the DataFrame with source + previously derived columns)
    - `pd` (pandas)
    - `np` (numpy)

    Returns ExecutionResult with the derived Series or error info.
    """

def compare_results(
    primary: pd.Series,
    qc: pd.Series,
    tolerance: float = 0.0,
) -> ComparisonResult:
    """Compare primary and QC derivation results.

    For numeric: allow tolerance.
    For string/bool: exact match.
    Returns match/mismatch with divergent row details.
    """
```

**Supporting models (define in this file):**

```python
class ExecutionResult(BaseModel, frozen=True):
    """Result of executing derivation code."""
    success: bool
    series_json: str | None = None     # Serialized result if success
    null_count: int = 0
    dtype: str = ""
    value_counts: dict[str, int] = {}  # Value distribution (for categorical)
    error: str | None = None           # Error message if failed
    execution_time_ms: float = 0.0

class ComparisonResult(BaseModel, frozen=True):
    """Result of comparing primary vs QC outputs."""
    variable: str
    verdict: QCVerdict
    match_count: int              # Rows that match
    mismatch_count: int           # Rows that differ
    total_rows: int
    divergent_indices: list[int]  # Row indices where values differ
    primary_sample: dict[str, str] = {}  # Aggregated: value distribution of divergent rows
    qc_sample: dict[str, str] = {}
    code_similarity: float = 0.0  # 0.0-1.0, AST similarity between implementations
```

**Implementation details:**
- `execute_derivation` uses `eval()` in a restricted namespace — only `df`, `pd`, `np` available
- Wraps execution in try/except to catch any error → returns `ExecutionResult(success=False, error=...)`
- Times execution via `time.perf_counter()`
- `compare_results` uses `pd.testing.assert_series_equal` internally (catches AssertionError for mismatch)
- `code_similarity` computed via `ast.dump()` comparison (normalize both ASTs, compute string similarity)

**Constraints:**
- `execute_derivation` NEVER returns raw DataFrame rows — only aggregates
- The restricted namespace prevents importing dangerous modules
- `compare_results` handles NaN-vs-NaN as equal (both are "missing")
- `divergent_indices` contains integer indices, not patient IDs

---

## 3.3 Verification

### `src/verification/__init__.py` (NEW)

Empty file.

### `src/verification/comparator.py` (NEW)

**Purpose:** Higher-level verification logic — wraps executor's comparison with AST similarity check and verdict decision. Imports `ExecutionResult`, `execute_derivation`, `compare_results` from `src/domain/executor.py` (domain layer — no layer violation).

**Public functions:**

```python
def verify_derivation(
    variable: str,
    coder_code: str,
    qc_code: str,
    df: pd.DataFrame,
    available_columns: list[str],
    tolerance: float = 0.0,
    independence_threshold: float = 0.8,
) -> VerificationResult:
    """Full verification of a derivation:
    1. Execute coder code → primary result
    2. Execute QC code → QC result
    3. Compare outputs
    4. Check code independence (AST similarity)
    5. Return verdict

    Returns VerificationResult with verdict, comparison details, and execution results.
    """

def compute_ast_similarity(code_a: str, code_b: str) -> float:
    """Compare two Python code strings via AST normalization.
    Returns 0.0 (completely different) to 1.0 (identical AST).
    Normalizes variable names and whitespace before comparison.
    """
```

**Supporting model:**

```python
class VerificationResult(BaseModel, frozen=True):
    """Complete result of the double-programming verification."""
    variable: str
    verdict: QCVerdict
    primary_result: ExecutionResult
    qc_result: ExecutionResult
    comparison: ComparisonResult | None = None   # None if either execution failed
    ast_similarity: float = 0.0
    recommendation: str = ""     # "auto_approve", "needs_debug", "insufficient_independence"
```

**Constraints:**
- If either execution fails → verdict is MISMATCH (can't verify)
- If both succeed but outputs differ → MISMATCH
- If both succeed and outputs match but AST similarity > threshold → INSUFFICIENT_INDEPENDENCE
- If both succeed, outputs match, and ASTs are different → MATCH

---

## 3.4 Tests

### `tests/unit/test_executor.py` (NEW)

**Purpose:** Tests for `src/domain/executor.py` (safe code execution + comparison).

**Tests:**
- `test_execute_derivation_simple_expression` — `"df['age'] * 2"` returns correct Series
- `test_execute_derivation_with_numpy` — `np.where(...)` works in namespace
- `test_execute_derivation_invalid_code_returns_error` — syntax error → `success=False`
- `test_execute_derivation_runtime_error_returns_error` — KeyError → `success=False`
- `test_execute_derivation_restricted_namespace` — `import os` → error (no builtins)
- `test_compare_results_exact_match` — identical Series → MATCH
- `test_compare_results_mismatch` — different values → MISMATCH with divergent indices
- `test_compare_results_nan_equals_nan` — both NaN → considered equal
- `test_compare_results_numeric_tolerance` — values within tolerance → MATCH

### `tests/unit/test_comparator.py` (NEW)

**Tests:**
- `test_verify_derivation_both_match` — same output, different AST → MATCH
- `test_verify_derivation_mismatch` — different output → MISMATCH
- `test_verify_derivation_identical_code_flags_independence` — same AST → INSUFFICIENT_INDEPENDENCE
- `test_verify_derivation_coder_fails` — coder error → MISMATCH
- `test_compute_ast_similarity_identical` — same code → 1.0
- `test_compute_ast_similarity_different` — totally different → <0.5
- `test_compute_ast_similarity_renamed_vars` — same logic, different var names → high similarity

### `tests/unit/test_workflow_fsm.py` (NEW)

**Purpose:** Tests for `src/engine/workflow_fsm.py` (FSM definition, transitions, callbacks).

**Tests:**
- `test_fsm_initial_state_is_created` — `WorkflowFSM("wf-1").current_state_value == "created"`
- `test_fsm_valid_transition_succeeds` — `fsm.start_spec_review()` moves to spec_review (check via `current_state_value`)
- `test_fsm_full_happy_path` — walk through created → spec_review → dag_built → deriving → verifying → review → auditing → completed
- `test_fsm_invalid_transition_raises` — calling `fsm.start_deriving()` from created raises `TransitionNotAllowed` (from `statemachine.exceptions`)
- `test_fsm_fail_from_any_state` — `fsm.fail()` works from spec_review, deriving, verifying, etc.
- `test_fsm_completed_is_final` — no transitions from completed
- `test_fsm_failed_is_final` — no transitions from failed
- `test_fsm_on_enter_state_creates_audit_record` — after transition, `fsm.audit_records` has entries
- `test_fsm_verify_to_debug_to_verify_loop` — verifying → debugging → verifying (retry loop)
- `test_fsm_verify_to_deriving_loop` — verifying → deriving (next variable in layer)

### `tests/unit/test_orchestrator.py` (NEW)

**Tests (do NOT call LLM — test orchestrator wiring and state):**
- `test_orchestrator_creates_dag_from_spec` — verify DAG built correctly for simple_mock
- `test_orchestrator_dag_layers` — verify layer assignment for simple_mock (3 layers)
- `test_workflow_status_is_strenum` — `WorkflowStatus` values are "completed" and "failed"
- `test_workflow_state_accumulates_derived_columns` — verify derived_df grows as columns are added
- `test_orchestrator_handles_spec_parse_error` — invalid spec path → FAILED state + error recorded
- `test_orchestrator_handles_dag_build_error` — circular dependency → FAILED state + error recorded

**Constraints:**
- Orchestrator tests that involve agents are integration tests (Phase 4)
- This phase tests only the FSM logic, DAG wiring, and error handling
