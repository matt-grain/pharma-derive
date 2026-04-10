# CDDE -- Clinical Data Derivation Engine

Agentic AI system for clinical data derivation (SDTM to ADaM) with regulatory-grade verification, human-in-the-loop approval, and full audit traceability.

Built as a take-home assignment for the Sanofi AI/ML Lead role.

## Quick Start

```bash
# Clone and install
git clone https://github.com/matt-grain/pharma-derive.git
cd pharma-derive
uv sync

# Run tests (148 tests, 89% coverage)
uv run pytest

# Start the Streamlit UI
uv run streamlit run src/ui/app.py

# Or with Docker
docker compose up --build
```

## Architecture

The system reads a transformation specification and structured clinical data (SDTM), uses a multi-agent workflow to generate, verify, and audit derivation logic, and outputs analysis-ready datasets (ADaM) with a complete audit trail. Five PydanticAI agents are composed via a finite state machine orchestrator, with HITL gates at each critical decision point. See the [Design Document](docs/design.md) for the full architecture narrative.

## Project Structure

```
src/
├── domain/        # Pure Python: models, DAG, spec parser
├── agents/        # 5 PydanticAI agents (Coder, QC, Debugger, Auditor, Spec)
├── engine/        # Orchestrator FSM, derivation runner, LLM gateway
├── verification/  # Double-programming QC comparison
├── persistence/   # SQLAlchemy repos (SQLite -> PostgreSQL)
├── audit/         # Append-only audit trail
└── ui/            # Streamlit HITL interface
```

## Key Features

- **Multi-agent workflow**: 5 specialized agents orchestrated via FSM
- **Double programming**: Independent coder + QC agents (regulatory standard)
- **Enhanced DAG**: Dependency order + lineage + provenance + audit per node
- **Data security**: Dual-dataset architecture -- agents never see patient data
- **HITL gates**: Spec review, code review, QC dispute, audit sign-off
- **Memory**: Short-term (per-run) + long-term (cross-run patterns, SQLite)
- **Traceability**: 3-layer audit (AgentLens + loguru + business trail)

## Data

Uses the [CDISC Pilot Study (cdiscpilot01)](https://github.com/phuse-org/phuse-scripts) -- a real Alzheimer's clinical trial dataset with SDTM + ADaM ground truth. The spec defines 7 real CDISC derivations (AGEGR1, TRTDUR, SAFFL, ITTFL, EFFFL, DISCONFL, DURDIS).

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `http://localhost:8650/v1` | AgentLens proxy URL |
| `LLM_API_KEY` | `not-needed-for-mailbox` | API key for LLM |
| `LLM_MODEL` | `cdde-agent` | Model name for LLM gateway |
| `DATABASE_URL` | `sqlite+aiosqlite:///cdde.db` | Database connection |

Copy `.env.example` to `.env` and adjust as needed.

## Development

```bash
uv sync --all-extras         # Install dev dependencies
uv run pytest                # Run tests
uv run ruff check . --fix    # Lint
uv run pyright .             # Type check
uv run lint-imports          # Architectural boundary check
```

## Quality

- 148 tests | 89% coverage
- pyright strict mode (0 errors)
- 19 import-linter contracts (layer boundaries)
- 10 custom pre-push architectural checks
- 18 pre-push hooks (all green)

## Deliverables

- [Design Document](docs/design.md) -- 3-page system design
- [Presentation](presentation/slides.md) -- 18 slides, 15-20 min
- [Architecture](ARCHITECTURE.md) -- Full technical reference
- [Requirements Analysis](docs/REQUIREMENTS.md) -- Problem framing + decisions

## Tech Stack

Python 3.13+ | PydanticAI | pandas | SQLAlchemy | python-statemachine | Streamlit | loguru | ruff | pyright
