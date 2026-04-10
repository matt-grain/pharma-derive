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

## Pre-Commit Hooks (18 total)

### On Every Commit (fast — 3 hooks)

| Hook | What It Catches |
|------|----------------|
| `ruff --fix` | Lint violations, auto-fixes imports/style |
| `ruff-format` | Formatting inconsistencies |
| `pyright` | Type errors (strict mode, 0 errors required) |

### On Every Push (thorough — 15 hooks)

| Hook | What It Catches |
|------|----------------|
| `pytest` | Test failures, coverage below 80% |
| `import-linter` | Layer boundary violations (19 contracts) |
| `radon cc` | Functions with cyclomatic complexity >= C |
| `radon mi` | Modules with poor maintainability index |
| `vulture` | Unused code (dead functions, variables, imports) |
| `check-domain-purity` | Framework imports in domain/ |
| `check-raw-sql-in-engine` | SQL strings or DB imports in engine/ |
| `check-patient-data-leaks` | `df.head()`, `df.to_csv()` in agent tools |
| `check-datetime-patterns` | Naive `datetime.now()`, deprecated `utcnow()` |
| `check-domain-no-ui-exceptions` | Streamlit/FastAPI imports in domain/agents/verification/audit |
| `check-engine-no-ui-exceptions` | Streamlit/FastAPI imports in engine/ |
| `check-repo-direct-instantiation` | Direct `Repository()` instantiation outside DI |
| `check-file-length` | Files >250, functions >40, classes >200 lines |
| `check-llm-gateway` | Direct OpenAIChatModel outside llm_gateway.py |
| `check-enum-discipline` | Raw string comparisons against enum values |

## Import-Linter Contracts (19 total)

| Contract | Rule | Status |
|----------|------|--------|
| `domain-no-agents` | domain/ cannot import from agents/ | ✅ |
| `domain-no-engine` | domain/ cannot import from engine/ | ✅ |
| `domain-no-verification` | domain/ cannot import from verification/ | ✅ |
| `domain-no-persistence` | domain/ cannot import from persistence/ | ✅ |
| `domain-no-audit` | domain/ cannot import from audit/ | ✅ |
| `agents-no-engine` | agents/ cannot import from engine/ | ✅ |
| `agents-no-verification` | agents/ cannot import from verification/ | ✅ |
| `agents-no-persistence` | agents/ cannot import from persistence/ | ✅ |
| `agents-no-audit` | agents/ cannot import from audit/ | ✅ |
| `verification-no-agents` | verification/ cannot import from agents/ (QC independence) | ✅ |
| `verification-no-engine` | verification/ cannot import from engine/ | ✅ |
| `verification-no-persistence` | verification/ cannot import from persistence/ | ✅ |
| `engine-no-persistence` | engine/ cannot import persistence/ (TYPE_CHECKING only) | ✅ |
| `persistence-no-agents` | persistence/ cannot import from agents/ | ✅ |
| `persistence-no-engine` | persistence/ cannot import from engine/ | ✅ |
| `audit-no-engine` | audit/ cannot import from engine/ | ✅ |
| `audit-no-persistence` | audit/ cannot import from persistence/ | ✅ |
| `audit-no-agents` | audit/ cannot import from agents/ | ✅ |
| `ui-no-persistence` | ui/ cannot import from persistence/ directly | ✅ |

## Custom Architectural Checks (10 total)

Located in `tools/pre_commit_checks/`. Each uses AST parsing (not regex) for accurate detection.

| Check | File | What It Enforces |
|-------|------|-----------------|
| Domain purity | `check_domain_purity.py` | domain/ may only import stdlib, pydantic, networkx, pandas, numpy |
| No SQL in engine | `check_raw_sql_in_engine.py` | engine/ must not contain SQL strings or import sqlalchemy |
| Patient data leaks | `check_patient_data_leaks.py` | Agent tools must not call `df.head()`, `df.to_csv()` etc. |
| Datetime patterns | `check_datetime_patterns.py` | Bans `datetime.utcnow()`, bare `datetime.now()`, stripped tzinfo |
| No UI exceptions (lower) | `check_domain_no_ui_exceptions.py` | domain/agents/verification/audit must not raise UI exceptions |
| No UI exceptions (engine) | `check_engine_no_ui_exceptions.py` | engine/ must raise domain exceptions, never HTTPException |
| Repo DI enforcement | `check_repo_direct_instantiation.py` | No direct `Repository()` instantiation outside DI |
| File/function/class length | `check_file_length.py` | Files >250 lines, functions >40 lines, classes >200 lines |
| LLM gateway enforcement | `check_llm_gateway.py` | No `OpenAIChatModel`/`OpenAIProvider` outside `llm_gateway.py` |
| Enum discipline | `check_enum_discipline.py` | No raw string comparisons against known enum values |

## Ruff Configuration

```toml
[tool.ruff]
target-version = "py313"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH", "RUF", "S"]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101"]
"src/domain/dag.py" = ["S101"]
"src/engine/orchestrator.py" = ["S101"]
"src/engine/derivation_runner.py" = ["S101"]
```

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

## Quality Metrics (Final — Phase 9)

| Metric | Value | Threshold |
|--------|-------|-----------|
| Test coverage | 89% | >= 80% |
| Tests passing | 148/148 | 100% |
| Pyright errors | 0 | 0 |
| Ruff violations | 0 | 0 |
| Import-linter contracts | 19/19 kept | 0 broken |
| Radon complexity | 1 function at C (12.0) | Flag C+ |
| Vulture dead code | 0 | 0 |
| Custom arch checks | 10/10 clean | 0 violations |
| Pre-push hooks | 18/18 green | All pass |

## Quality History

| Phase | Tests | Coverage | Contracts | Notes |
|-------|-------|----------|-----------|-------|
| Phase 1 (domain) | 25 | — | 7/7 | Domain models, DAG, spec parser |
| Phase 2 (agents) | 52 | — | 7/7 | 5 PydanticAI agents, shared tools, LLM gateway |
| Phase 3 (engine) | 87 | 95% | 7/7 | WorkflowFSM, derivation runner, executor, comparator |
| Phase 4 (persistence) | 118 | 85% | 17/17 | SQLAlchemy repos, audit trail, integration tests |
| Review fix | 118 | 85% | 17/17 | 18 findings fixed, 3 new StrEnums, gateway enforced |
| Phase 5 (CDISC) | 125 | 85% | 17/17 | XPT loader, ADSL spec, 3 new pre-commit checks |
| Phase 6 (review) | 148 | 89% | 19/19 | File splits, enums, DebugContext, 30 new tests, AAA markers |
| Phase 7 (Streamlit) | 148 | 89% | 19/19 | HITL UI, AgentLens theme, DAG visualization |
| Phase 8 (docs) | 148 | 89% | 19/19 | Design doc (3 pages), Marp slides (18 slides) |
| Phase 9 (Docker) | 148 | 89% | 19/19 | Dockerfile, compose, README |
