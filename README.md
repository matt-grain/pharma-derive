# CDDE -- Clinical Data Derivation Engine

Agentic AI system for clinical data derivation (SDTM to ADaM) with regulatory-grade verification, human-in-the-loop approval, and full audit traceability.

Built as a take-home assignment for the Sanofi AI/ML Lead role.

## 2-minute demo

**Prereqs:** Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js 20+.

```bash
# Clone this repo + AgentLens side-by-side
git clone https://github.com/matt-grain/pharma-derive.git
git clone https://github.com/matt-grain/AgentLens.git
# One-time setup
cd pharma-derive
uv sync
(cd frontend && npm install)
cp .env.example .env
uv run python scripts/download_data.py   # fetches CDISC Pilot SDTM + ADaM XPT files into data/
```

Four terminals:

```bash
# 1. AgentLens proxy (mailbox mode — no real LLM)
cd ../AgentLens && uv run agentlens serve --mode mailbox --traces-dir ../pharma-derive/traces
# 2. Backend
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
# 3. Frontend
(cd frontend && npm run dev)
# 4. Canned mailbox responder (plays the LLM)
uv run python scripts/mailbox_cdisc.py
```

In the browser at `http://localhost:3000`:

1. **New Workflow** → `adsl_cdiscpilot01.yaml` → **Start**
2. When the banner turns amber (`human_review`), click **Approve**
3. Check the **Data** tab (SDTM + ADaM panels) and `GET /api/v1/workflows/{id}/ground_truth` for the comparison against the official CDISC reference — see `docs/GROUND_TRUTH_REPORT.md`.

**~90 seconds end-to-end.** Swap the responder for a live Claude key via `LLM_BASE_URL` + `LLM_API_KEY` to run with real LLM calls.

## Quick Start

```bash
# Clone and install
git clone https://github.com/matt-grain/pharma-derive.git
cd pharma-derive
uv sync
cd frontend && npm install && cd ..

# Run tests (318 backend + 14 frontend = 332 total)
uv run pytest
(cd frontend && npm test)

# Start the backend API (terminal 1)
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

# Start the frontend dev server (terminal 2)
cd frontend && npm run dev

# Or with Docker (all-in-one)
docker compose up --build
```

- Backend API + docs: `http://localhost:8000/docs`
- Frontend SPA: `http://localhost:3000`
- MCP endpoint (for LLM agents): `http://localhost:8000/mcp/mcp`

## Architecture

The system reads a YAML transformation specification and structured clinical data (SDTM), uses a multi-agent workflow to generate, verify, and audit derivation logic, and outputs analysis-ready datasets (ADaM) with a complete audit trail. Five PydanticAI agents are composed via a YAML-driven `PipelineInterpreter` (auto-generating the FSM from the pipeline steps), with one deep HITL gate supporting per-variable approve / reject / code override. See the [Design Document](docs/Clinical%20Data%20Derivation%20Engine.docx) and [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full architecture narrative.

## Project Structure

```
src/
├── config/        # Settings (pydantic-settings), LLM gateway, logging
├── domain/        # Pure Python: models, DAG, exceptions, spec parser, pipeline models
├── agents/        # 5 PydanticAI agents + tools/ (sandbox, LTM queries, tracing)
├── engine/        # PipelineInterpreter, PipelineFSM, step_executors, derivation_runner
├── verification/  # Double-programming QC comparison
├── persistence/   # SQLAlchemy async repos: Pattern, Feedback, QCHistory, WorkflowState
├── audit/         # Append-only audit trail + JSON / HTML export
└── api/           # FastAPI + FastMCP routers, workflow manager, HITL endpoints
frontend/          # Vite + React + TanStack Query SPA (Status, DAG, Code, Data, Audit tabs)
config/
├── agents/        # YAML agent configs (coder, qc_programmer, debugger, auditor, spec_interpreter)
└── pipelines/     # YAML pipeline definitions (express, clinical_derivation, enterprise)
```

## Key Features

- **Multi-agent workflow**: 5 specialized PydanticAI agents dispatched by a YAML-driven `PipelineInterpreter`
- **Double programming**: Independent coder + QC agents run via `asyncio.gather` with isolated contexts (ICH E6)
- **Enhanced DAG**: Dependency order + lineage + provenance + approval trail per node
- **Data security**: Dual-dataset architecture — agents see schema + synthetic sample only; real data stays in local tools
- **HITL gate (depth over count)**: one deep `human_review` gate with three actions — per-variable approve-with-feedback, reject-with-reason, in-place code override
- **Long-term memory**: 3 tools surface past evidence to the coder with authority ranking (`query_feedback` > `query_qc_history` > `query_patterns`)
- **Ground truth check**: built-in step compares derived output against a reference ADaM XPT and emits a per-variable verdict report
- **Resilience**: per-step checkpointing + `POST /rerun` so backend crashes mid-run are recoverable
- **Traceability**: 3-layer audit (AgentLens OTel + loguru + append-only business audit trail, JSON + HTML export)

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

- 332 tests (318 backend + 14 frontend), all passing
- pyright strict mode (0 errors), ruff clean
- 19 import-linter contracts (layer boundaries enforced)
- 10 custom pre-push architectural checks (`tools/pre_commit_checks/`)
- 18 pre-push hooks (all green on every push)
- See [`QUALITY.md`](QUALITY.md) for the full metric history across all phases.

## Deliverables

- [Design Document](docs/Clinical%20Data%20Derivation%20Engine.docx) — system design (Word)
- [Ground Truth Report](docs/GROUND_TRUTH_REPORT.md) — empirical validation against the official CDISC Pilot ADSL reference
- [Presentation](presentation/CDDE_Presentation.pptx) — panel slide deck
- [Architecture](ARCHITECTURE.md) — full technical reference
- [Requirements Analysis](docs/REQUIREMENTS.md) — problem framing + decisions

## Tech Stack

**Backend:** Python 3.13+ · PydanticAI · FastAPI · FastMCP 3.0 · SQLAlchemy async · pandas · pyreadstat · loguru · uv
**Frontend:** Vite · React · TanStack Query · shadcn/ui · Tailwind
**Observability / LLM proxy:** AgentLens (OpenTelemetry)
**Quality gates:** ruff · pyright (strict) · pytest · import-linter · radon · vulture · 10 custom AST checks

## Diagrams

Generate Mermaid diagrams (FSM state diagram + orchestration sequence diagrams):

```bash
uv run python scripts/generate_diagrams.py
```

`fsm_states.mmd` is **auto-generated from `config/pipelines/clinical_derivation.yaml`** (the same YAML the runtime interprets, so the diagram cannot drift from actual behavior). The other two diagrams are hand-authored — they describe behavioral flow rather than static step structure. All three render to SVG via `npx @mermaid-js/mermaid-cli` (requires Node.js).

| Diagram | Description |
|---------|-------------|
| `fsm_states.svg` | Pipeline FSM — auto-generated from `clinical_derivation.yaml` step definitions |
| `orchestration_sequence.svg` | Full workflow: User → API → PipelineInterpreter → StepExecutors → LTM / FS |
| `derivation_detail.svg` | Per-variable loop: LTM read → Coder + QC parallel → comparator → debugger → audit |

