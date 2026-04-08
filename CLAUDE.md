# CLAUDE.md — Sanofi AI-ML Lead Homework

## Project Overview

Agentic AI system for clinical data derivation (SDTM → ADaM), built as a take-home assignment for the Sanofi AI-ML Lead role. This is NOT a throwaway POC — it follows production-grade engineering practices.

## Tech Stack

- **Language:** Python 3.13+
- **Agent framework:** PydanticAI
- **LLM:** Claude API (via `anthropic` SDK)
- **Observability:** AgentLens (OTel-based tracing)
- **Data:** pandas + pyreadstat (for XPT files)
- **UI:** Streamlit (HITL approval workflows)
- **Package manager:** uv
- **Testing:** pytest
- **Linting:** ruff
- **Type checking:** pyright (strict mode) and ty
- **CI:** GitHub Actions
- **Containerization**: TBD

## Project Structure

```
homework/
├── CLAUDE.md                  # This file
├── ARCHITECTURE.md            # System architecture (mandatory, keep updated)
├── decisions.md               # Architecture Decision Records
├── pyproject.toml             # Dependencies + tool configs
├── uv.lock                    # Pinned dependencies
├── .github/workflows/ci.yml   # Lint + typecheck + test
├── docs/
│   ├── homework.md            # Original assignment
│   ├── REQUIREMENTS.md        # Requirements analysis & decision log
│   └── design.md              # Design document (2-4 pages, deliverable)
├── data/
│   ├── sdtm/                  # CDISC pilot SDTM input (XPT files)
│   └── adam/                  # CDISC pilot ADaM ground truth (XPT files)
├── specs/                     # Transformation specifications (YAML)
├── src/
│   ├── __init__.py
│   ├── domain/                # Core domain: DAG, derivation rules, models
│   ├── agents/                # Agent definitions (PydanticAI agents + shared tools)
│   ├── engine/                # Orchestration: workflow, DAG execution, memory
│   ├── verification/          # QC: double programming, comparison, reporting
│   ├── audit/                 # Traceability: lineage, audit trail, export
│   └── ui/                    # Streamlit HITL interface
├── tests/
│   ├── unit/                  # Unit tests (domain logic, DAG, derivations)
│   ├── integration/           # Integration tests (agent workflows, end-to-end)
│   └── conftest.py            # Shared fixtures
└── presentation/              # Slide deck for 15-20 min panel presentation
```

## Development Rules

### Architecture

- **Layered architecture:** domain → agents → engine → ui. No layer may import from a layer above it.
  - `domain/` — Pure Python, no framework dependencies. DAG, derivation models, spec parsing.
  - `agents/` — PydanticAI agent definitions and tasks. Depends on domain.
  - `engine/` — Orchestration, workflow state machine, memory management. Depends on domain + agents.
  - `verification/` — QC comparison logic. Depends on domain only.
  - `audit/` — Lineage export, audit trail generation. Depends on domain only.
  - `ui/` — Streamlit pages. Depends on everything (top of the stack).
- **No circular imports.** If you need something from a higher layer, you're modeling it wrong.
- **Domain models are plain dataclasses or Pydantic models.** No framework-specific types in the domain layer.

### Code Quality

- **ruff:** Enforce on every file. No `# noqa` without a comment explaining why.
- **pyright:** Strict mode. No `Any` without justification. No `# type: ignore` without a comment.
- **No bare `except`.** Always catch specific exceptions.
- **No mutable default arguments.**
- **Functions > 30 lines:** Flag for review. Consider splitting.
- **Files > 200 lines:** Flag for review. Consider splitting.

### Type Safety

- All function signatures must have full type annotations (params + return).
- Use `TypeAlias`, `TypeVar`, `Protocol` where they add clarity.
- Pydantic models for all data crossing boundaries (specs, audit records, API responses).
- `str` enums for status fields (derivation status, QC result, approval state).

### Testing

- **Target: >80% coverage on `domain/`, `verification/`, and `engine/`.**
- Unit tests for all derivation logic — these are the critical path (wrong derivation = wrong drug approval).
- Unit tests for DAG construction and topological sort.
- Integration tests for agent workflows (can mock LLM calls).
- Test names: `test_<what>_<condition>_<expected>` (e.g., `test_age_group_missing_age_returns_none`).
- Use `conftest.py` for shared fixtures (sample SDTM data, sample specs).
- **No mocking of core derivation logic.** Mock LLM calls, not data transforms.

### Agent Design

- Each agent has a single, well-defined responsibility (see REQUIREMENTS.md Q4).
- Agent prompts live in the `agents/` module, not inline strings scattered across the codebase.
- All LLM calls go through a single gateway function — no direct `anthropic.Client()` calls in agent code.
- Agent outputs are validated against Pydantic schemas before being passed downstream.
- The QC agent MUST NOT have access to the primary coder agent's output (regulatory independence).

### DAG & Derivation Rules

- The DAG is built at runtime from the transformation spec, never hardcoded.
- Each DAG node stores: source variables, derivation rule, generated code, agent provenance, QC status, human approval.
- Topological sort before execution — fail loudly if cycles are detected.
- Each derivation is a pure function: `(input_df, params) -> Series`. No side effects.

### Memory Design

- **Short-term (workflow state):** JSON file per run. Tracks current step, intermediate outputs, pending approvals. Cleared on new run.
- **Long-term (validated patterns):** SQLite database. Stores approved derivation patterns, human feedback, QC history. Persists across runs.
- Memory reads/writes go through a repository interface, not direct file/DB access.

### Traceability & Audit

- Every derivation step produces an audit record: timestamp, agent, input hash, output hash, rule applied, QC result, human approval.
- Audit trail is append-only. No record deletion.
- Export to JSON for inspection and to HTML (via AgentLens) for presentation.

### Dependencies

- Minimize external packages. Justify each one.
- All deps pinned via `uv.lock`.
- No floating versions in `pyproject.toml` — use `>=X.Y,<X+1` bounds.

### Git Discipline

- Meaningful commit messages explaining WHY, not just what.
- No secrets in commits (API keys, tokens). Use `.env` + `.gitignore`.
- Separate commits for: setup, domain logic, agents, tests, UI, docs.

### Documentation

- `ARCHITECTURE.md` — Mandatory. Update when structure changes.
- `decisions.md` — ADR for every non-trivial technical choice.
- `REQUIREMENTS.md` — Already started. Captures problem framing and thought process.
- `docs/design.md` — Deliverable design document (2-4 pages).
- Code comments only for WHY, never for WHAT.

### What NOT To Do

- No Jupyter notebooks as primary deliverables. Code lives in `.py` files.
- No `print()` debugging left in code. Use `logging`.
- No `TODO` without a rationale (since this is a bounded homework, TODOs should note "production extension" scope).
- No catch-all `utils.py` or `helpers.py`. If a function is used once, it stays where it's used.
- No LangChain. We use PydanticAI and understand what's under the hood.
