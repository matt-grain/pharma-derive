# Code Quality & Architectural Enforcement

This document tracks all quality gates, linters, and architectural checks in the CDDE project.

## Tooling Stack

| Tool | Version | Purpose | Stage |
|------|---------|---------|-------|
| **ruff** | 0.15+ | Linting + formatting (replaces flake8, isort, black) | pre-commit |
| **pyright** | 1.1+ | Strict type checking | pre-commit |
| **pytest** | 8.0+ | Tests + coverage (>= 80% enforced) | pre-push |
| **import-linter** | 2.11+ | Layer boundary enforcement | pre-push |
| **radon** | 6.0+ | Cyclomatic complexity + maintainability index | pre-push |
| **vulture** | 2.16+ | Dead code detection (>= 80% confidence) | pre-push |
| **pre-commit** | 4.5+ | Git hook orchestrator | commit + push |

## Pre-Commit Hooks

### On Every Commit (fast)

| Hook | What It Catches |
|------|----------------|
| `ruff --fix` | Lint violations, auto-fixes imports/style |
| `ruff-format` | Formatting inconsistencies |
| `pyright` | Type errors (strict mode, 0 errors required) |

### On Every Push (thorough)

| Hook | What It Catches |
|------|----------------|
| `pytest` | Test failures, coverage below 80% |
| `import-linter` | Layer boundary violations (see contracts below) |
| `radon cc` | Functions with cyclomatic complexity >= C |
| `radon mi` | Modules with poor maintainability index |
| `vulture` | Unused code (dead functions, variables, imports) |
| `check-domain-purity` | Framework imports in domain/ (PydanticAI, loguru, SQLAlchemy, etc.) |
| `check-raw-sql-in-engine` | SQL strings or DB imports in engine/ |
| `check-patient-data-leaks` | `df.head()`, `df.to_csv()` etc. in agent tool functions |
| `check-datetime-patterns` | Naive `datetime.now()`, deprecated `utcnow()`, stripped tzinfo |
| `check-domain-no-ui-exceptions` | Streamlit/FastAPI imports or raises in domain/agents/verification/audit |
| `check-engine-no-ui-exceptions` | Streamlit/FastAPI imports or raises in engine/ |
| `check-repo-direct-instantiation` | Direct `Repository()` instantiation outside persistence/ and tests/ |
| `check-file-length` | Files >200 lines, functions >30 lines, classes >150 lines |
| `check-llm-gateway` | Direct OpenAIChatModel/OpenAIProvider construction outside llm_gateway.py |
| `check-enum-discipline` | Raw string comparisons against known enum values |

## Import-Linter Contracts

### Active (Phases 1-4)

| Contract | Rule | Status |
|----------|------|--------|
| `domain-no-agents` | domain/ cannot import from agents/ | **ACTIVE** |
| `domain-no-engine` | domain/ cannot import from engine/ | **ACTIVE** |
| `domain-no-verification` | domain/ cannot import from verification/ | **ACTIVE** |
| `agents-no-engine` | agents/ cannot import from engine/ | **ACTIVE** |
| `agents-no-verification` | agents/ cannot import from verification/ | **ACTIVE** |
| `verification-no-agents` | verification/ cannot import from agents/ (QC independence) | **ACTIVE** |
| `verification-no-engine` | verification/ cannot import from engine/ | **ACTIVE** |
| `domain-no-persistence` | domain/ cannot import from persistence/ | **ACTIVE** |
| `domain-no-audit` | domain/ cannot import from audit/ | **ACTIVE** |
| `agents-no-persistence` | agents/ cannot import from persistence/ | **ACTIVE** |
| `agents-no-audit` | agents/ cannot import from audit/ | **ACTIVE** |
| `engine-no-persistence` | engine/ cannot import persistence/ directly (TYPE_CHECKING only) | **ACTIVE** |
| `verification-no-persistence` | verification/ cannot import from persistence/ | **ACTIVE** |
| `persistence-no-agents` | persistence/ cannot import from agents/ | **ACTIVE** |
| `persistence-no-engine` | persistence/ cannot import from engine/ | **ACTIVE** |
| `audit-no-engine` | audit/ cannot import from engine/ | **ACTIVE** |
| `audit-no-persistence` | audit/ cannot import from persistence/ | **ACTIVE** |

**Total: 17 contracts, 0 broken.**

### Planned (Phase 6)

| Contract | Rule | Status |
|----------|------|--------|
| `audit-no-agents` | audit/ cannot import from agents/ | **PLANNED** |
| `ui-no-persistence` | ui/ cannot import from persistence/ directly | **PLANNED** |

## Custom Architectural Checks

Located in `tools/pre_commit_checks/`. Each uses AST parsing (not regex) for accurate detection.

| Check | File | What It Enforces |
|-------|------|-----------------|
| Domain purity | `check_domain_purity.py` | domain/ may only import stdlib, pydantic, networkx, pandas, numpy. Bans PydanticAI, statemachine, loguru, SQLAlchemy, streamlit, fastapi, httpx |
| No SQL in engine | `check_raw_sql_in_engine.py` | engine/ must not contain SQL strings or import sqlalchemy/sqlite3/asyncpg. Repos injected via DI |
| Patient data leaks | `check_patient_data_leaks.py` | Agent tool functions (with `RunContext` param) must not call `df.head()`, `df.to_csv()`, `df.to_string()` etc. — prevents PII leakage to LLM |
| Datetime patterns | `check_datetime_patterns.py` | Bans `datetime.utcnow()` (deprecated), bare `datetime.now()` (naive), `.replace(tzinfo=None)` (strips tz). Audit timestamps must be tz-aware |
| No UI exceptions (lower layers) | `check_domain_no_ui_exceptions.py` | domain/, agents/, verification/, audit/ must not import or raise streamlit/fastapi/starlette exceptions |
| No UI exceptions (engine) | `check_engine_no_ui_exceptions.py` | engine/ must raise domain exceptions, never UI-tier (HTTPException, Streamlit errors) |
| Repo DI enforcement | `check_repo_direct_instantiation.py` | No `Repository()` instantiation or `from persistence import *Repository` in domain/agents/engine/verification/audit — repos injected via constructor |
| File/function/class length | `check_file_length.py` | Files >200 lines, functions >30 lines, classes >150 lines in src/ |
| LLM gateway enforcement | `check_llm_gateway.py` | No direct `OpenAIChatModel`/`OpenAIProvider` construction outside `llm_gateway.py` |
| Enum discipline | `check_enum_discipline.py` | No raw string comparisons against known enum values (match, completed, coder, etc.) — use StrEnum members |

## Ruff Configuration

```toml
[tool.ruff]
target-version = "py313"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH", "RUF", "S"]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101"]
"src/engine/orchestrator.py" = ["S101"]
"src/engine/derivation_runner.py" = ["S101"]
```

Excludes: `scripts/`, `prototypes/`

## Pyright Configuration

```toml
[tool.pyright]
pythonVersion = "3.13"
typeCheckingMode = "strict"
reportMissingTypeStubs = false
```

## CI Pipeline

`.github/workflows/ci.yml` mirrors pre-commit hooks:
```
uv sync --dev → ruff check → ruff format --check → pyright → pytest --cov
```

## Quality Metrics (Current — Phase 5)

| Metric | Value | Threshold |
|--------|-------|-----------|
| Test coverage | 85% | >= 80% |
| Tests passing | 125/125 | 100% |
| Pyright errors | 0 | 0 |
| Ruff violations | 0 | 0 |
| Import-linter contracts | 17/17 kept | 0 broken |
| Radon complexity | 1 function at C (13.0) | Flag C+ |
| Vulture dead code | 0 | 0 |
| Custom arch checks | 10 checks, 2 clean + 1 with known deferred violations | 0 new |

## Quality History

| Phase | Tests | Coverage | Contracts | Notes |
|-------|-------|----------|-----------|-------|
| Phase 1 (domain) | 25 | — | 7/7 | Domain models, DAG, spec parser |
| Phase 2 (agents) | 52 | — | 7/7 | 5 PydanticAI agents, shared tools, LLM gateway |
| Phase 3 (engine) | 87 | 95% | 7/7 | WorkflowFSM, derivation runner, executor, comparator |
| Phase 4 (persistence) | 118 | 85% | 17/17 | SQLAlchemy repos, audit trail, integration tests |
| Phase 4→5 (review fix) | 118 | 85% | 17/17 | 18 review findings fixed, 3 new StrEnums, gateway enforced |
| Phase 5 (CDISC data) | 125 | 85% | 17/17 | XPT loader, ADSL spec (7 derivations), 3 new pre-commit checks |
