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

## Import-Linter Contracts

### Active (Phase 1-3)

| Contract | Rule | Status |
|----------|------|--------|
| `domain-no-agents` | domain/ cannot import from agents/ | **ACTIVE** |
| `domain-no-engine` | domain/ cannot import from engine/ | **ACTIVE** |
| `domain-no-verification` | domain/ cannot import from verification/ | **ACTIVE** |
| `agents-no-engine` | agents/ cannot import from engine/ | **ACTIVE** |
| `agents-no-verification` | agents/ cannot import from verification/ | **ACTIVE** |
| `verification-no-agents` | verification/ cannot import from agents/ (QC independence) | **ACTIVE** |
| `verification-no-engine` | verification/ cannot import from engine/ | **ACTIVE** |

### Commented Out (Phase 4 — uncomment when modules exist)

| Contract | Rule | Status |
|----------|------|--------|
| `domain-no-persistence` | domain/ cannot import from persistence/ | **COMMENTED** — waiting for `src/persistence/` |
| `domain-no-audit` | domain/ cannot import from audit/ | **COMMENTED** — waiting for `src/audit/` |
| `agents-no-persistence` | agents/ cannot import from persistence/ | **COMMENTED** |
| `agents-no-audit` | agents/ cannot import from audit/ | **COMMENTED** |
| `engine-no-persistence` | engine/ cannot import persistence/ directly (use DI) | **COMMENTED** |
| `verification-no-persistence` | verification/ cannot import from persistence/ | **COMMENTED** |
| `persistence-no-agents` | persistence/ cannot import from agents/ | **COMMENTED** |
| `persistence-no-engine` | persistence/ cannot import from engine/ | **COMMENTED** |
| `audit-no-engine` | audit/ cannot import from engine/ | **COMMENTED** |
| `audit-no-persistence` | audit/ cannot import from persistence/ | **COMMENTED** |

**Action required:** When implementing Phase 4, uncomment contracts in `.importlinter` and verify they pass.

## Custom Architectural Checks

Located in `tools/pre_commit_checks/`. Each uses AST parsing (not regex) for accurate detection.

### Active

| Check | File | What It Enforces |
|-------|------|-----------------|
| Domain purity | `check_domain_purity.py` | domain/ may only import stdlib, pydantic, networkx, pandas, numpy. Bans PydanticAI, statemachine, loguru, SQLAlchemy, streamlit, fastapi, httpx |
| No SQL in engine | `check_raw_sql_in_engine.py` | engine/ must not contain SQL strings or import sqlalchemy/sqlite3/asyncpg. Repos injected via DI |
| Patient data leaks | `check_patient_data_leaks.py` | Agent tool functions (with `RunContext` param) must not call `df.head()`, `df.to_csv()`, `df.to_string()` etc. — prevents PII leakage to LLM |
| Datetime patterns | `check_datetime_patterns.py` | Bans `datetime.utcnow()` (deprecated), bare `datetime.now()` (naive), `.replace(tzinfo=None)` (strips tz). Audit timestamps must be tz-aware |
| No UI exceptions (lower layers) | `check_domain_no_ui_exceptions.py` | domain/, agents/, verification/, audit/ must not import or raise streamlit/fastapi/starlette exceptions |
| No UI exceptions (engine) | `check_engine_no_ui_exceptions.py` | engine/ must raise domain exceptions, never UI-tier (HTTPException, Streamlit errors) |
| Repo DI enforcement | `check_repo_direct_instantiation.py` | No `Repository()` instantiation or `from persistence import *Repository` in domain/agents/engine/verification/audit — repos injected via constructor |

### Planned (adapt when needed)

| Check | Priority | When | What It Would Enforce |
|-------|----------|------|-----------------------|
| Exception coverage | Low | Phase 4 | All domain exceptions caught somewhere in engine/ (informational) |

## Ruff Configuration

```toml
[tool.ruff]
target-version = "py313"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH", "RUF"]
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

## Quality Metrics (Current)

| Metric | Value | Threshold |
|--------|-------|-----------|
| Test coverage | 95% | >= 80% |
| Tests passing | 87/87 | 100% |
| Pyright errors | 0 | 0 |
| Ruff violations | 0 | 0 |
| Import-linter contracts | 7/7 kept | 0 broken |
| Radon complexity | 1 function at C (13.0) | Flag C+ |
| Vulture dead code | 0 | 0 |
