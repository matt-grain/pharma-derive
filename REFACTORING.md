# Refactoring Tracker — Phase 10: Production Hardening

Code review findings from manual audit. Each item maps to an evaluation criterion in the Sanofi homework rubric.

## Status Legend

- ⬜ Not started
- 🔧 In progress
- ✅ Fixed
- ❌ Won't fix (with rationale)

## Findings

| # | Category | Finding | Severity | Eval Criteria | Status | Phase |
|---|----------|---------|----------|--------------|--------|-------|
| R01 | **Exceptions** | `assert` used as runtime guards in `orchestrator.py`, `dag.py`. Replaced with `WorkflowStateError`, `DAGError`. | Critical | §9.7 Implementation Quality, §11.C Reliability | ✅ | 10.2 |
| R02 | **Exceptions** | Bare `except Exception` in `orchestrator.py:run()`. Split into `CDDEError` + `Exception` with `logger.exception`. Added `_rollback_derived_columns()` to drop partial derivations on failure. | High | §11.C Reliability | ✅ | 10.2 |
| R03 | **Repository** | Zero error handling in repos. `_flush()` wraps writes, `_execute()` wraps reads — both catch `OperationalError` → `RepositoryError`. `pool_pre_ping=True` + pool config for PostgreSQL. | High | §11.C Reliability, §10.D Failure Handling | ✅ | 10.2 |
| R04 | **DAG Fragility** | Manual `dag.update_node()` calls. Replaced with atomic `DerivationRunResult` → `dag.apply_run_result()`. `update_node` removed, `apply_run_result` uses clean `getattr`/`setattr` loop. | High | §9.7 Implementation Quality | ✅ | 10.2 |
| R05 | **Agent Metadata** | `AgentName.AUDITOR` hardcoded. All agents now have `name=` param; orchestrator uses `auditor_agent.name`. | Medium | §9.7 Implementation Quality | ✅ | 10.2 |
| R06 | **Tool Tracing** | Bare tool functions. Added `@traced_tool` decorator with loguru timing + error logging. | Medium | §10.H Observability, §9.7 Quality | ✅ | 10.2 |
| R07 | **Module Focus** | `tools.py` 190 lines. Split into `tools/` package: `sandbox.py`, `inspect_data.py`, `execute_code.py`, `tracing.py`. | Medium | §9.7 Implementation Quality | ✅ | 10.1 |
| R08 | **Module Focus** | `repositories.py` 176 lines. Split into 5 files with `BaseRepository`. | Medium | §9.7 Implementation Quality | ✅ | 10.1 |
| R09 | **Misplaced Modules** | `llm_gateway.py`, `logging.py` in `engine/`. Moved to `src/config/`. | Low | §9.7 Implementation Quality | ✅ | 10.1 |
| R10 | **Misplaced Modules** | `workflow_fsm.py`, `workflow_models.py` in `engine/`. Moved to `src/domain/`. | Low | §9.7 Implementation Quality | ✅ | 10.1 |
| R11 | **Config Duplication** | `DATABASE_URL` and `LLM_BASE_URL` duplicated. Consolidated into `src/config/constants.py`. `llm_gateway.py` now imports from constants (residual duplicate fixed). | Low | §9.7 Implementation Quality | ✅ | 10.3 |
| R12 | **Type Safety** | Missing type hints in `get_stats()`. Added `total: int`, `matches: int` annotations. | Low | §9.7 Implementation Quality | ✅ | 10.3 |
| R13 | **Docstrings** | Inconsistent coverage. Added docstrings to all public repo methods. | Low | §9.7 Implementation Quality | ✅ | 10.3 |
| R14 | **Ruff Config** | Stale S101 ignores. Removed; added T20, C4, RET rules. CPY001 skipped (overhead vs homework scope). | Low | §9.7 Implementation Quality | ✅ | 10.3 |
| R15 | **LLM Gateway** | Multiple `create_llm()` calls. Added module-level cache with `reset_llm_cache()` for tests. | Low | §9.7 Implementation Quality | ✅ | 10.3 |

## Future Items (Not in Phase 10)

These are larger architectural changes identified during review, tracked but deferred:

| # | Category | Finding | Notes |
|---|----------|---------|-------|
| F01 | **UI/API Split** | Streamlit UI and orchestrator are coupled. Production needs FastAPI backend + thin UI client for independent scaling/deployment. | Requires new API layer |
| F02 | **YAML-Driven Pipeline** | Orchestrator steps are hardcoded in `run()`. Steps could be configurable via YAML + Step protocol for extensibility. | Good for platform thinking story |
| F03 | **YAML-Driven FSM** | FSM states/transitions could be generated from YAML config, shared with pipeline config. | Coupled with F02 |
| F04 | **Mermaid Diagrams** | Generate sequence diagram for orchestration flow. Good for presentation. | Presentation enhancement |
| F05 | **Exec Sandbox** | Token-based blocklist in `execute_code` is naive (`"import"` blocks `"important"`). AST-based check or subprocess sandbox would be more reliable. | Security hardening |
| F06 | **YAML Agent Definitions** | Agent prompts, retries, model, and tools are hardcoded in Python. A YAML config per agent + factory would make agents study-configurable (different prompts per therapeutic area) without touching code. Maps to `OUTPUT_TYPE_MAP` registry for type resolution. | §11.A Platform Thinking — same engine, different YAML = different study |
