# Phase 3 — Orchestration Engine + Verification

**Dependencies:** Phase 1 (domain models, DAG) + Phase 2 (agents, LLM gateway)
**Agent:** `python-fastapi`
**Estimated files:** 8

This phase implements the orchestration layer — the workflow FSM, DAG-ordered executor, and QC comparator. This is where PydanticAI agents are composed into the clinical derivation pipeline using standard Python async patterns.

---

## 3.1 Orchestrator (Workflow FSM)

### `src/engine/orchestrator.py` (NEW)

**Purpose:** Top-level workflow controller. Manages the FSM states (CREATED → SPEC_REVIEW → ... → COMPLETED) and dispatches agents.

**Public class:**

```python
class DerivationOrchestrator:
    """Orchestrates the full derivation workflow."""

    def __init__(
        self,
        spec_path: str | Path,
        llm_base_url: str = "http://localhost:8650/v1",
    ) -> None:
        """Initialize with spec path and LLM config."""

    @property
    def state(self) -> WorkflowState:
        """Current workflow state (read-only view)."""

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
class WorkflowState(BaseModel):
    """Current state of the workflow."""
    workflow_id: str                     # UUID
    step: WorkflowStep                   # FSM state
    spec: TransformationSpec | None = None
    dag: DerivationDAG | None = None     # Not serializable — store as reference
    current_variable: str | None = None
    audit_records: list[AuditRecord] = []
    errors: list[str] = []
    started_at: str | None = None        # ISO timestamp
    completed_at: str | None = None

class WorkflowResult(BaseModel):
    """Final output of a workflow run."""
    workflow_id: str
    study: str
    status: str                          # "completed" or "failed"
    derived_variables: list[str]
    qc_summary: dict[str, str]           # variable → verdict
    audit_records: list[AuditRecord]
    audit_summary: AuditSummary | None = None
    errors: list[str]
    duration_seconds: float
```

**Constraints:**
- `WorkflowState.step` transitions follow the FSM in ARCHITECTURE.md
- Invalid transitions raise `ValueError` (e.g., can't go from CREATED to DERIVING)
- Each step logs via `loguru` at INFO level
- Each step appends to `audit_records`
- `_run_derivation` uses `asyncio.gather` for Coder + QC (as validated in prototype)
- `_run_dag_layer` uses `asyncio.gather` for all variables in the layer
- Agent `model` is set via `agent.override(model=create_llm(llm_base_url))`
- NO HITL gates in this phase — auto-approve everything (HITL added in UI phase later)

---

## 3.2 DAG Executor

### `src/engine/executor.py` (NEW)

**Purpose:** Executes generated derivation code safely on a DataFrame.

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
class ExecutionResult(BaseModel):
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

**Purpose:** Higher-level verification logic — wraps executor's comparison with AST similarity check and verdict decision.

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

### `tests/unit/test_orchestrator.py` (NEW)

**Tests (do NOT call LLM — test FSM logic only):**
- `test_workflow_state_initial_step` — starts at CREATED
- `test_workflow_state_transitions` — valid transitions succeed
- `test_workflow_state_invalid_transition_raises` — CREATED → DERIVING raises ValueError
- `test_orchestrator_creates_dag_from_spec` — verify DAG built correctly for simple_mock
- `test_orchestrator_dag_layers` — verify layer assignment for simple_mock (3 layers)

**Constraints:**
- Orchestrator tests that involve agents are integration tests (Phase 4)
- This phase tests only the FSM logic and DAG wiring
