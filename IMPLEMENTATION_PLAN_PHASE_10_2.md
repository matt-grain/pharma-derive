# Phase 10.2 — Wiring: Use New Structures

**Depends on:** Phase 10.1 (domain exceptions, DerivationRunResult, BaseRepository, module moves complete)
**Agent:** `python-fastapi`
**Refactoring items:** R01, R02, R03, R04, R05, R06
**Goal:** Wire up the new types and structures into existing code. Behavioral changes — each module gets proper error handling, atomic DAG updates, tool tracing.

---

## 1. Replace `assert` with domain exceptions — `src/engine/orchestrator.py` (MODIFY)

**Change:** Replace every `assert self._state.X is not None` with a proper `WorkflowStateError` raise.
**Exact changes:**

```python
# BEFORE (line 132):
assert self._state.spec is not None

# AFTER:
if self._state.spec is None:
    raise WorkflowStateError("spec", "build_dag")
```

Apply to ALL assert statements in orchestrator:
- `_step_build_dag`: `self._state.spec` (line 132), `self._state.derived_df` (line 133)
- `_step_derive_all`: `self._state.dag` (line 141)
- `_derive_variable`: `self._state.dag` (line 150), `self._state.derived_df` (line 151)
- `_record_derivation_outcome`: `self._state.dag` (line 164)
- `_step_audit`: `self._state.dag` (line 196), `self._state.spec` (line 197)

**Also:** Narrow the `except Exception` in `run()` (line 88) to catch `CDDEError` specifically, and add a separate handler for unexpected errors that logs the full traceback:
```python
except CDDEError as exc:
    logger.error("Workflow {wf_id} failed: {err}", wf_id=self._state.workflow_id, err=exc)
    self._state.errors.append(str(exc))
    self._fsm.fail(str(exc))
except Exception as exc:
    logger.exception("Workflow {wf_id} unexpected error", wf_id=self._state.workflow_id)
    self._state.errors.append(f"Unexpected: {exc}")
    self._fsm.fail(str(exc))
```

**Import:** `from src.domain.exceptions import CDDEError, WorkflowStateError`

---

## 2. Replace `assert` in `src/domain/dag.py` (MODIFY)

**Change:** The `assert self._layers is not None` in the `layers` property (line 60) should use a guard:
```python
@property
def layers(self) -> list[list[str]]:
    if self._layers is None:
        self._compute_layers()
    if self._layers is None:
        raise DAGError("Failed to compute topological layers")
    return list(self._layers)
```
**Import:** `from src.domain.exceptions import DAGError`

---

## 3. Add `dag.apply_run_result()` — `src/domain/dag.py` (MODIFY)

**Purpose:** Single atomic method to update a DAG node from a `DerivationRunResult`, replacing 6+ scattered `update_node()` calls.
**Add method to `DerivationDAG`:**
```python
def apply_run_result(self, result: DerivationRunResult) -> None:
    """Atomically update a DAG node from a derivation run result.
    
    This is the ONLY way derivation_runner should update the DAG —
    prevents inconsistent partial updates from scattered update_node() calls.
    """
    node = self._nodes[result.variable]
    node.status = result.status
    if result.coder_code is not None:
        node.coder_code = result.coder_code
    if result.coder_approach is not None:
        node.coder_approach = result.coder_approach
    if result.qc_code is not None:
        node.qc_code = result.qc_code
    if result.qc_approach is not None:
        node.qc_approach = result.qc_approach
    if result.qc_verdict is not None:
        node.qc_verdict = result.qc_verdict
    if result.approved_code is not None:
        node.approved_code = result.approved_code
    if result.debug_analysis is not None:
        node.debug_analysis = result.debug_analysis
```
**Import:** `from src.domain.models import DerivationRunResult`
**Constraint:** Keep the existing `update_node()` for backward compat (used in tests), but `derivation_runner.py` must exclusively use `apply_run_result()`.

---

## 4. Refactor `src/engine/derivation_runner.py` to use `DerivationRunResult` (MODIFY)

**Purpose:** Replace scattered `dag.update_node()` calls with building a `DerivationRunResult` and calling `dag.apply_run_result()`.

**Change `run_variable()`:**
```python
async def run_variable(...) -> None:
    node = dag.get_node(variable)
    # Build result progressively
    coder, qc_code = await _run_coder_and_qc(...)
    vr = verify_derivation(...)

    if vr.verdict == QCVerdict.MATCH:
        result = DerivationRunResult(
            variable=variable,
            status=DerivationStatus.APPROVED,
            coder_code=coder.python_code,
            qc_code=qc_code.python_code,
            qc_verdict=vr.verdict,
            approved_code=coder.python_code,
        )
        dag.apply_run_result(result)
        _apply_series_to_df(variable, vr.primary_result, derived_df)
        return

    # Debug path
    analysis = await _debug_variable(...)
    approved_code = _resolve_approved_code(analysis, coder, qc_code)
    
    if approved_code:
        exec_result = execute_derivation(derived_df, approved_code, list(derived_df.columns))
        if exec_result.success and exec_result.series_json:
            result = DerivationRunResult(
                variable=variable,
                status=DerivationStatus.APPROVED,
                coder_code=coder.python_code,
                qc_code=qc_code.python_code,
                qc_verdict=vr.verdict,
                approved_code=approved_code,
                debug_analysis=analysis.root_cause,
            )
            dag.apply_run_result(result)
            _apply_series_to_df(variable, exec_result, derived_df)
            return

    # Mismatch — no approved code
    result = DerivationRunResult(
        variable=variable,
        status=DerivationStatus.QC_MISMATCH,
        coder_code=coder.python_code,
        qc_code=qc_code.python_code,
        qc_verdict=vr.verdict,
        debug_analysis=analysis.root_cause if 'analysis' in dir() else None,
    )
    dag.apply_run_result(result)
```

**Extract helper (with null guard — `series_json` is `str | None` on `ExecutionResult`):**
```python
def _apply_series_to_df(variable: str, exec_result: ExecutionResult, derived_df: pd.DataFrame) -> None:
    """Deserialize approved series and add to working DataFrame."""
    if exec_result.series_json is None:
        raise DerivationError(variable, "Execution produced no result data")
    series: pd.Series[object] = pd.read_json(  # type: ignore[assignment]
        StringIO(exec_result.series_json),
        typ="series",
    )
    derived_df[variable] = series
```
**Import:** `from src.domain.exceptions import DerivationError`

**Remove:** All direct `dag.update_node()` calls from this file.
**Import:** `from src.domain.models import DerivationRunResult`

**Note on asserts:** `derivation_runner.py` itself has NO assert statements. The asserts for `dag` and `derived_df` are in `orchestrator.py._derive_variable()` which calls `run_variable()` — those are handled in §1 above. The rewrite of `run_variable()` here receives `dag` and `derived_df` as function parameters (not `self._state` attributes), so no None guards are needed — the caller is responsible.

---

## 5. Repository error handling — `src/persistence/base_repo.py` (MODIFY)

**Purpose:** Add try/except with logging around DB flush operations.
**Change the `_flush()` method:**
```python
from loguru import logger
from sqlalchemy.exc import IntegrityError, OperationalError

async def _flush(self) -> None:
    """Flush session with error wrapping and logging."""
    try:
        await self._session.flush()
    except IntegrityError as exc:
        logger.error("Integrity error during flush: {err}", err=exc)
        raise RepositoryError("flush", f"Integrity constraint violated: {exc}") from exc
    except OperationalError as exc:
        logger.error("Operational error during flush: {err}", err=exc)
        raise RepositoryError("flush", f"Database operational error: {exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected error during flush")
        raise RepositoryError("flush", f"Unexpected: {exc}") from exc
```
**Import:** `from src.domain.exceptions import RepositoryError`

---

## 6. Tool tracing — add `src/agents/tools/tracing.py` (NEW)

**Purpose:** Decorator/wrapper that adds structured logging and timing to tool functions.
```python
"""Tool tracing — adds structured logging and timing to PydanticAI tools."""
from __future__ import annotations

import functools
import time
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

from loguru import logger

P = ParamSpec("P")
R = TypeVar("R")


def traced_tool(
    name: str,
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """Decorator that logs tool entry, exit, timing, and errors."""
    def decorator(fn: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            logger.info("Tool {name} started", name=name)
            start = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                logger.info("Tool {name} completed in {ms:.1f}ms", name=name, ms=elapsed)
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                logger.error("Tool {name} failed after {ms:.1f}ms: {err}", name=name, ms=elapsed, err=exc)
                raise
        return wrapper
    return decorator
```

**Apply to tools:**
In `src/agents/tools/inspect_data.py`:
```python
@traced_tool("inspect_data")
async def inspect_data(ctx: RunContext[CoderDeps]) -> str: ...
```

In `src/agents/tools/execute_code.py`:
```python
@traced_tool("execute_code")
async def execute_code(ctx: RunContext[CoderDeps], code: str) -> str: ...
```

**Constraints:**
- Decorator preserves function signature for PydanticAI tool registration
- Timing in milliseconds
- Structured loguru fields (not f-strings)

---

## 7. Agent metadata instead of hardcoded enum — `src/engine/orchestrator.py` (MODIFY)

**Change:** In `_step_audit()`, replace hardcoded `AgentName.AUDITOR` with the agent's own name:
```python
# BEFORE (line 211-214):
self._audit_trail.record(
    variable="",
    action=AuditAction.AUDIT_COMPLETE,
    agent=AgentName.AUDITOR,
    details={"auto_approved": str(result.output.auto_approved)},
)

# AFTER:
self._audit_trail.record(
    variable="",
    action=AuditAction.AUDIT_COMPLETE,
    agent=auditor_agent.name or "auditor",
    details={"auto_approved": str(result.output.auto_approved)},
)
```

**Also:** Add `name=` to each agent definition in `src/agents/`:
- `auditor.py`: `Agent("test", name="auditor", ...)`
- `derivation_coder.py`: `Agent("test", name="coder", ...)`
- `qc_programmer.py`: `Agent("test", name="qc_programmer", ...)`
- `debugger.py`: `Agent("test", name="debugger", ...)`
- `spec_interpreter.py`: `Agent("test", name="spec_interpreter", ...)`

**Note:** Keep the `AgentName` enum for now — it's still used in `workflow_fsm.py` and `_record_derivation_outcome`. The enum is not wrong for those cases (orchestrator's own identity). Only remove the pattern of hardcoding *agent* names via a separate enum.

---

## 8. Update tests

**Modified test files:**
- `tests/unit/test_orchestrator.py` — update for new exception types, verify `WorkflowStateError` is raised
- `tests/unit/test_dag.py` — add test for `apply_run_result()`, test `DAGError` on bad layers
- `tests/unit/test_derivation_runner.py` — update for `DerivationRunResult`-based flow
- `tests/unit/test_persistence.py` — add tests for `RepositoryError` on flush failure
- `tests/unit/test_agent_tools.py` — verify tracing decorator doesn't break tool signatures
- `tests/unit/test_agent_config.py` — verify `agent.name` is set on all agents

**New tests to add:**
- `test_workflow_state_error_raised_when_spec_none` — orchestrator raises, not asserts
- `test_apply_run_result_updates_all_node_fields` — DAG atomicity
- `test_apply_run_result_partial_fields` — only set fields are updated
- `test_repository_error_on_integrity_violation` — flush wrapping works
- `test_traced_tool_logs_timing` — tracing decorator captures timing

**Verification:**
1. `uv run ruff check . --fix && uv run ruff format .`
2. `uv run pyright .`
3. `uv run pytest --tb=short -q` — all tests must pass (148 + new tests)
