# Phase 10.3 — Polish: Quality Quick Wins

**Depends on:** Phase 10.2 (all behavioral changes complete, imports stable)
**Agent:** `python-fastapi`
**Refactoring items:** R11, R12, R13, R14, R15
**Goal:** Type safety, docstrings, config consolidation, ruff cleanup. No structural changes.

---

## 1. Consolidate DATABASE_URL default — `src/config/constants.py` (NEW)

**Purpose:** Single source of truth for default configuration values.
```python
"""Shared configuration constants."""
from __future__ import annotations

from typing import Final

DEFAULT_DATABASE_URL: Final[str] = "sqlite+aiosqlite:///cdde.db"
DEFAULT_LLM_BASE_URL: Final[str] = "http://localhost:8650/v1"
```

**Modify `src/persistence/database.py`:**
```python
# BEFORE:
url = database_url or os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///cdde.db")

# AFTER:
from src.config.constants import DEFAULT_DATABASE_URL
url = database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
```

**Modify `src/factory.py`:**
Same change — use `DEFAULT_DATABASE_URL` constant.

**Modify `src/engine/orchestrator.py` (constructor default):**
```python
# BEFORE:
llm_base_url: str = "http://localhost:8650/v1"

# AFTER:
from src.config.constants import DEFAULT_LLM_BASE_URL
llm_base_url: str = DEFAULT_LLM_BASE_URL
```

---

## 2. Type hints in `src/persistence/qc_history_repo.py` — `get_stats()` (MODIFY)

**Change:** Add explicit type annotations to intermediate variables:
```python
async def get_stats(self, variable: str | None = None) -> QCStats:
    base: Select[tuple[int]] = select(func.count()).select_from(QCHistoryRow)
    match_stmt: Select[tuple[int]] = select(func.count()).select_from(QCHistoryRow).where(
        QCHistoryRow.verdict == QCVerdict.MATCH.value
    )
    if variable:
        base = base.where(QCHistoryRow.variable == variable)
        match_stmt = match_stmt.where(QCHistoryRow.variable == variable)
    total_result: Result[tuple[int]] = await self._session.execute(base)
    total: int = total_result.scalar() or 0
    match_result: Result[tuple[int]] = await self._session.execute(match_stmt)
    matches: int = match_result.scalar() or 0
    ...
```
**Import:** `from sqlalchemy import Result, Select`
**Note:** The exact SQLAlchemy generic types may need adjustment based on what pyright accepts. Use `Result[Any]` and `Select[Any]` if strict generics cause issues, with a justification comment.

---

## 3. Docstrings on all public methods (MODIFY multiple files)

**Rule:** Every public method (no `_` prefix) gets a one-line docstring. Private methods get docstrings only if non-obvious.

**Files to check and update:**
- `src/domain/dag.py` — `update_node()` needs docstring (currently has one, verify)
- `src/domain/exceptions.py` — all classes need docstrings (created in Phase 10.1)
- `src/persistence/base_repo.py` — `_flush()` already has one
- `src/persistence/pattern_repo.py` — `store()`, `query_by_type()` need docstrings
- `src/persistence/feedback_repo.py` — `store()`, `query_by_variable()` need docstrings
- `src/persistence/qc_history_repo.py` — `store()`, `get_stats()` need docstrings
- `src/persistence/workflow_state_repo.py` — `save()`, `load()`, `delete()` need docstrings
- `src/engine/orchestrator.py` — `_derive_variable()` (flagged in review as missing)
- `src/engine/derivation_runner.py` — `run_variable()` already has one, check helpers
- `src/agents/tools/inspect_data.py` — `inspect_data()` already has one
- `src/agents/tools/execute_code.py` — `execute_code()` already has one
- `src/agents/tools/tracing.py` — `traced_tool()` needs docstring

**Constraints:**
- Comments explain WHY, not WHAT
- Don't restate the function signature
- Keep docstrings to 1-2 lines max

---

## 4. Ruff config cleanup — `pyproject.toml` (MODIFY)

**Changes:**
1. Remove S101 per-file-ignores for `orchestrator.py` and `derivation_runner.py` (asserts replaced):
```toml
[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101"]
"src/domain/dag.py" = ["S101"]  # assert guards cached computation invariant
# REMOVED: orchestrator.py and derivation_runner.py — asserts replaced with exceptions
```

2. Add `"T20"` (flake8-print) to catch any leftover `print()` statements:
```toml
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH", "RUF", "S", "T20"]
```

3. Consider adding `"C4"` (flake8-comprehensions) and `"RET"` (flake8-return) for extra quality:
```toml
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH", "RUF", "S", "T20", "C4", "RET"]
```

**Note on T20 vs sandbox.py:** `src/agents/tools/sandbox.py` contains `"print": print` in `_SAFE_BUILTINS` — this is a dict reference to the builtin, not a `print()` call. T20 only flags `print(...)` call expressions, not references, so this should be fine. If ruff does flag it, add a per-file-ignore: `"src/agents/tools/sandbox.py" = ["T20"]` with comment `# print is a sandbox builtin reference, not a call`.

**Note on CPY001:** CPY001 (copyright) requires `ruff.lint.flake8-copyright` config — evaluate if the overhead is worth it for a homework project. If skipped, document in REFACTORING.md as "won't fix" with rationale.

---

## 5. LLM gateway caching — `src/config/llm_gateway.py` (MODIFY)

**Change:** Cache the LLM model instance so `create_llm()` doesn't create a new provider on every call:
```python
_cached_model: OpenAIChatModel | None = None
_cached_key: str | None = None

def create_llm(
    model_name: str = _DEFAULT_MODEL,
    base_url: str = _DEFAULT_BASE_URL,
    api_key: str = _DEFAULT_API_KEY,
) -> OpenAIChatModel:
    """Create or return cached PydanticAI LLM model."""
    global _cached_model, _cached_key
    resolved_url = os.environ.get("LLM_BASE_URL", base_url)
    resolved_key = os.environ.get("LLM_API_KEY", api_key)
    resolved_model = os.environ.get("LLM_MODEL", model_name)
    
    cache_key = f"{resolved_url}:{resolved_key}:{resolved_model}"
    if _cached_model is not None and _cached_key == cache_key:
        return _cached_model
    
    provider = OpenAIProvider(base_url=resolved_url, api_key=resolved_key)
    _cached_model = OpenAIChatModel(resolved_model, provider=provider)
    _cached_key = cache_key
    return _cached_model
```
**Constraint:** Thread-safe enough for asyncio (single-threaded event loop). If tests need fresh models, add `reset_llm_cache()` test helper.

---

## 6. Update `ARCHITECTURE.md` project structure (MODIFY)

**Change:** Update the Project Structure section to reflect the new layout:
```
src/
├── __init__.py
├── factory.py                 # DI factory for orchestrator
├── config/                    # Infrastructure configuration
│   ├── __init__.py
│   ├── constants.py           # Shared defaults (DATABASE_URL, LLM_BASE_URL)
│   ├── llm_gateway.py         # LLM model construction (AgentLens proxy)
│   └── logging.py             # loguru configuration
├── domain/                    # Pure domain: models, DAG, FSM, spec parsing
│   ├── __init__.py
│   ├── models.py              # DerivationRule, DAGNode, DerivationRunResult, etc.
│   ├── exceptions.py          # CDDEError, WorkflowStateError, DerivationError, etc.
│   ├── dag.py                 # DAG construction, topological sort, apply_run_result
│   ├── spec_parser.py         # YAML spec → DerivationRule objects
│   ├── executor.py            # Safe code execution + result comparison
│   ├── source_loader.py       # CSV/XPT file loading (I/O but domain-adjacent)
│   ├── synthetic.py           # Privacy-safe synthetic data generation
│   ├── workflow_fsm.py        # Workflow state machine (python-statemachine)
│   └── workflow_models.py     # WorkflowState, WorkflowResult
├── agents/                    # PydanticAI agent definitions
│   ├── __init__.py
│   ├── deps.py                # Shared CoderDeps dependency container
│   ├── tools/                 # Agent tools (split by responsibility)
│   │   ├── __init__.py        # Re-exports: inspect_data, execute_code
│   │   ├── sandbox.py         # Safe builtins, blocked tokens, namespace builder
│   │   ├── inspect_data.py    # Data inspection tool (schema, nulls, ranges)
│   │   ├── execute_code.py    # Sandboxed code execution tool
│   │   └── tracing.py         # @traced_tool decorator for observability
│   ├── spec_interpreter.py
│   ├── derivation_coder.py
│   ├── qc_programmer.py
│   ├── debugger.py
│   └── auditor.py
├── engine/                    # Orchestration layer
│   ├── __init__.py
│   ├── orchestrator.py        # Workflow controller, agent dispatch
│   └── derivation_runner.py   # Per-variable coder+QC+verify+debug loop
├── verification/              # QC / double programming
│   ├── __init__.py
│   └── comparator.py
├── audit/                     # Traceability
│   ├── __init__.py
│   └── trail.py
├── persistence/               # Database layer
│   ├── __init__.py            # Re-exports all repos
│   ├── database.py            # Engine + session factory
│   ├── orm_models.py          # SQLAlchemy table definitions
│   ├── base_repo.py           # BaseRepository with error wrapping
│   ├── pattern_repo.py        # PatternRepository
│   ├── feedback_repo.py       # FeedbackRepository
│   ├── qc_history_repo.py     # QCHistoryRepository
│   └── workflow_state_repo.py # WorkflowStateRepository
└── ui/                        # Streamlit HITL
    ├── ...
```

**Also update:** Layer Responsibilities section — add `config/` layer description:
```
### config/ — Infrastructure Configuration
- **Does:** Configure LLM gateway, logging, shared constants
- **Must NOT:** Contain business logic or domain models
- **Depends on:** Nothing (leaf layer)
```

---

## 7. Update `decisions.md` (MODIFY)

**Add ADR:**
```markdown
## 2026-04-10 — Production Hardening Refactor (Phase 10)

**Status:** accepted
**Context:** Code review identified PoC shortcuts that cost points on §9.7 Implementation Quality and §11.C Reliability: assert-as-guards, zero DB error handling, fragile manual DAG updates, misplaced modules, no tool tracing.
**Decision:** Refactor in 3 sub-phases: (1) new types + module restructure, (2) wire behavioral changes, (3) quality polish. No feature changes — pure structural improvement.
**Alternatives considered:** Fixing only critical items (asserts + DB errors) and leaving module structure. Rejected because evaluators also grade on "code structure, modularity, readability" — the module layout issues are visible to a reviewer scanning the tree.
**Consequences:** ~25 files touched. Import paths change (mitigated by __init__.py re-exports). Test count increases. Module structure now matches ARCHITECTURE.md claims.
```

---

## Verification

After all Phase 10.3 changes:
1. `uv run ruff check . --fix && uv run ruff format .`
2. `uv run pyright .`
3. `uv run pytest --tb=short -q` — all tests must pass
4. `uv run pytest --cov=src --cov-report=term-missing` — verify coverage ≥89%
5. Manual review: ARCHITECTURE.md project structure matches actual `src/` layout
