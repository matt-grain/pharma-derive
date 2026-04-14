# CDDE -- Clinical Data Derivation Engine

Agentic AI system for clinical data derivation (SDTM to ADaM) with regulatory-grade verification, human-in-the-loop approval, and full audit traceability.

## 2-minute demo

**Prereqs:** Python 3.13+ with [uv](https://docs.astral.sh/uv/getting-started/installation/) and Node.js 20+ with [pnpm](https://pnpm.io/installation).

```bash
# Clone this repo + AgentLens side-by-side
git clone https://github.com/matt-grain/pharma-derive.git
git clone https://github.com/matt-grain/AgentLens.git
# One-time setup
cd pharma-derive
uv sync
(cd frontend && pnpm install)
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
(cd frontend && pnpm dev)
# 4. Canned mailbox responder (plays the LLM)
uv run python scripts/mailbox_cdisc.py
```

In the browser at `http://localhost:3000`:

1. **New Workflow** → `adsl_cdiscpilot01.yaml` → **Start**
2. When the banner turns amber (`human_review`), click **Approve**
3. Check the **Data** tab (SDTM + ADaM panels) and `GET /api/v1/workflows/{id}/ground_truth` for the comparison against the official CDISC reference — see `docs/GROUND_TRUTH_REPORT.md`.

**~90 seconds end-to-end.** Swap the responder for a live Claude key via `LLM_BASE_URL` + `LLM_API_KEY` to run with real LLM calls.

## Quick Start — Docker stack (WSL2 / Linux)

Runs the full stack — nginx reverse proxy + PostgreSQL + AgentLens + backend + frontend — as 5 containers. Verified on Docker CE in WSL2 Ubuntu. For the host-native flow (no Docker), see the 2-minute demo above.

**Prereqs:** Docker Engine 25+ with compose v2, [uv](https://docs.astral.sh/uv/getting-started/installation/) (for the data download step), and [AgentLens](https://github.com/matt-grain/AgentLens) cloned side-by-side at `../AgentLens`.

### 1. Populate the data directory (one-off)

The CDISC Pilot SDTM + ADaM XPT files are mounted read-only into the backend container — they are NOT baked into the image (PHI hygiene). On a fresh clone you must run the download step **before** `docker compose up`, otherwise the mount will be empty. **Run this from WSL** if you're using Docker CE inside WSL:

```bash
cd pharma-derive
uv run python scripts/download_data.py   # populates ./data/{sdtm,adam}/cdiscpilot01/
```

### 2. Build the images + start the stack

```bash
# One-off: build the AgentLens image from the sibling repo (cached thereafter)
docker build -t agentlens:latest ../AgentLens

# Build pharma-derive backend + frontend images via compose
docker compose build

# Start all 5 services in the background
docker compose up -d
docker compose ps         # verify everything is healthy
```

### 3. Access the running stack

| URL | What |
|---|---|
| `http://localhost:8080/` | React SPA (via nginx → frontend) |
| `http://localhost:8080/health` | Backend health (via nginx) |
| `http://localhost:8080/api/v1/specs/` | REST API (via nginx) |
| `http://localhost:8080/mcp/mcp` | FastMCP transport for LLM agents (via nginx) |
| `http://localhost:8000/docs` | Backend Swagger UI (direct, bypasses nginx) |
| `http://localhost:8650/mailbox` | AgentLens mailbox API (direct, for manual LLM replies) |

`nginx` is published on **8080**, not 80, because rootless Docker in WSL2 cannot bind privileged ports.

### 4. Shut down

```bash
docker compose down         # stop + remove containers, keep the PostgreSQL volume
docker compose down -v      # also drop the PostgreSQL volume (fresh start next time)
```

## Debugging & Audit

All the regulatorily-interesting outputs land on the **host filesystem** via named volume mounts, not inside the containers — you can read them directly with any host-side tool, even after a `docker compose down`.

### Where to look

| What | Where | Format | Who writes it |
|---|---|---|---|
| **Derived ADaM datasets** (per workflow) | `./output/{workflow_id}_adam.csv`<br>`./output/{workflow_id}_adam.parquet` | CSV + Parquet | `export_adam` builtin step |
| **Audit trail** (append-only, per workflow) | `./output/{workflow_id}_audit.json` | JSON | `audit/trail.py` at pipeline completion |
| **SDTM source snapshot** (per workflow) | `./output/{workflow_id}_source.csv` | CSV | `parse_spec` builtin (Phase 18.1) |
| **AgentLens OTel traces** (per LLM call) | `./traces/*.json` | JSON (OTel spans) | AgentLens proxy |
| **Backend application logs** (uvicorn + loguru) | `docker compose logs backend` | stdout/stderr | accessed via the Docker log driver |
| **PostgreSQL data** | named volume `postgres_data` | — | SQLAlchemy async writes |

### Reading an audit trail for a specific workflow

```bash
jq . output/{workflow_id}_audit.json                                    # full audit trail
jq '.[] | .action + " " + .variable' output/{workflow_id}_audit.json    # event summary
```

The audit trail is append-only — every `AuditRecord` has timestamp, agent, action, variable, input hash, output hash, QC result, and human approval context. Matches the 21 CFR Part 11 §11.10(e) shape.

### Following backend logs live

```bash
docker compose logs -f backend              # live tail
docker compose logs --since 5m backend      # last 5 minutes
docker compose logs backend | grep ERROR    # just errors
```

In production these would be shipped to Splunk / Elasticsearch / Loki via a sidecar or the Docker logging driver. The dev stack relies on `docker compose logs` directly.

### Generating an AgentLens HTML report from a trace

Each LLM call recorded by the AgentLens proxy lands in `./traces/<hash>.json`. Render one into a browsable HTML report — agent trajectory, tool calls, timing breakdown, token usage per step:

```bash
# Host-native (uv — easiest if AgentLens is cloned locally at ../AgentLens)
uv run --directory ../AgentLens agentlens evaluate \
    /absolute/path/to/pharma-derive/traces/<hash>.json \
    --html \
    --output /absolute/path/to/pharma-derive/traces/report_<hash>.html

# Or via a throw-away container if you don't want Python on the host
docker run --rm \
    -v "$(pwd)/traces:/app/traces:ro" \
    -v "$(pwd)/traces:/app/out" \
    agentlens:latest \
    agentlens evaluate /app/traces/<hash>.json --html --output /app/out/report_<hash>.html
```

Open the resulting `report_<hash>.html` in a browser.

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
uv sync --all-extras                                 # Install dev dependencies
uv run pytest                                        # Run tests
uv run pytest --cov=src --cov-report=term-missing    # Run tests + coverage summary
uv run pytest --cov=src --cov-report=html            # Run tests + HTML coverage report (htmlcov/index.html)
uv run ruff check . --fix                            # Lint
uv run pyright .                                     # Type check
uv run lint-imports                                  # Architectural boundary check
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

