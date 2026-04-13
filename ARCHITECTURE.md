# Architecture

## Overview

**Clinical Data Derivation Engine (CDDE)** — an agentic AI system that automates the SDTM → ADaM derivation step of the clinical trial data pipeline, with built-in verification (double programming), human-in-the-loop approval, and full audit traceability.

The system reads a transformation specification and structured clinical data (SDTM), uses a multi-agent workflow to generate, verify, and audit derivation logic, and outputs analysis-ready datasets (ADaM) with a complete audit trail.

## Orchestration Architecture — Core Component

The orchestration layer is the heart of the system. It composes multiple AI agents into a clinical derivation workflow with regulatory-grade verification. This section explains the architecture of this core component; later sections describe the wrapping layers (HITL API, UI, deployment).

### Why PydanticAI + Custom Orchestrator

The clinical derivation workflow requires five orchestration patterns:

| Pattern | What It Does | Framework Requirement |
|---------|-------------|----------------------|
| **Sequential** | Spec → DAG → Derive → Audit | Basic — any framework handles this |
| **Fan-out / Fan-in** | Derive independent variables in parallel | True `asyncio.gather` — must launch N agents concurrently |
| **Concurrent + Compare** | Coder and QC produce independent implementations, then compare | Two agents on same input with isolated contexts, structured output for programmatic comparison |
| **Retry with Escalation** | QC mismatch → Debugger → if unresolved → human | Error handling with fallback chain |
| **HITL Gate** | Workflow pauses for human review/approval | Web-UI integration (Streamlit), not CLI stdin |

We evaluated CrewAI and PydanticAI against these requirements:

- **CrewAI** failed on three: `async_execution` has known bugs (PR #2466, missed/duplicated tasks), `human_input` is CLI stdin only (no web UI), and structured output is bolted on rather than native.
- **PydanticAI** passed all five in prototype validation (5/5 tests passed, see `prototypes/PLAN.md`):
  - True parallel agents via `asyncio.gather` (two requests arrived within 0.01s)
  - Structured Pydantic output with automatic validation and retry
  - Typed dependency injection via `RunContext[DepsType]`
  - Multi-turn tool use (inspect → execute → return)
  - Composable — no opinionated orchestration that fights our workflow

**Decision:** PydanticAI provides the **agent abstractions** (definition, tools, typed I/O, validation). The orchestration layer composes PydanticAI agents using standard Python async patterns (`asyncio.gather`, state machine, repository interfaces). This is not a "custom framework" — it's PydanticAI's intended composition model applied to clinical workflow rules.

This separation means:
- PydanticAI handles what it's good at: LLM communication, tool binding, output validation
- The orchestration layer handles what's domain-specific: clinical workflow rules, regulatory verification, human approval gates
- Either layer can be swapped independently (different agent framework, different workflow engine)

### Core Architecture Diagram

```
┌─ HITL API (FastAPI/Streamlit) ───────────────────────────────────────────┐
│  POST /approve/{gate_id}     GET /pending      WS /status               │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
┌─ Orchestration Engine ───────────┼───────────────────────────────────────┐
│  (PydanticAI composition + Python async)                                 │
│                                                                          │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────┐  ┌────────────────┐  │
│  │ Workflow FSM │  │ DAG Engine  │  │ HITL Gates │  │ Logging        │  │
│  │ (state       │  │ (networkx   │  │ (DB-backed │  │ (loguru:       │  │
│  │  machine)    │  │  topo sort) │  │  polling)  │  │  orchestration │  │
│  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘  │  + functional) │  │
│         │                 │               │         └────────────────┘  │
│         └─────────────────┴───────────────┘                             │
│                           │                                              │
│               ┌───────────┴───────────┐                                  │
│               │    asyncio.gather     │  ← Fan-out / Fan-in              │
│               │  (parallel dispatch)  │                                  │
│               └───────────┬───────────┘                                  │
│                           │                                              │
│          ┌────────────────┼──────────────┐                               │
│          │                │              │                                │
│    ┌─────▼─────┐   ┌─────▼─────┐   ┌────▼──────┐                        │
│    │ PydanticAI│   │ PydanticAI│   │ PydanticAI│  ...                   │
│    │ Agent     │   │ Agent     │   │ Agent     │                        │
│    │ (Coder)   │   │ (QC)      │   │ (Auditor) │                        │
│    │           │   │           │   │           │                        │
│    │ tools:    │   │ tools:    │   │ tools:    │                        │
│    │ inspect   │   │ inspect   │   │ export    │                        │
│    │ execute   │   │ execute   │   │ check     │                        │
│    └─────┬─────┘   └─────┬─────┘   └─────┬─────┘                        │
│          │               │               │                               │
│          └───────────────┴───────────────┘                               │
│                          │                                               │
│                    All LLM calls via:                                    │
│          ┌───────────────▼─────────────────┐                             │
│          │        LLM Gateway              │                             │
│          │  (OpenAI-compatible endpoint)   │                             │
│          │  + trace emission (OTel/JSON)   │                             │
│          └───────────────┬─────────────────┘                             │
│                          │                                               │
│  ┌─ Memory ──────────────┼──────────────────────────────────────────┐    │
│  │                       │                                          │    │
│  │  ┌─────────────────┐  │  ┌──────────────────────────────────┐    │    │
│  │  │ Short-Term       │  │  │ Long-Term                        │    │    │
│  │  │ (per-run state)  │  │  │ (cross-run knowledge)            │    │    │
│  │  │                  │  │  │                                  │    │    │
│  │  │ • workflow state │  │  │ • validated derivation patterns  │    │    │
│  │  │ • intermediate   │  │  │ • human feedback history         │    │    │
│  │  │   outputs        │  │  │ • QC match/mismatch patterns    │    │    │
│  │  │ • pending        │  │  │ • reusable code snippets        │    │    │
│  │  │   approvals      │  │  │                                  │    │    │
│  │  │                  │  │  │ Retrieval: by variable type,     │    │    │
│  │  │ Storage: JSON    │  │  │ by spec similarity, by study    │    │    │
│  │  │ Lifecycle: per   │  │  │ Storage: SQLite (→ PostgreSQL)  │    │    │
│  │  │ workflow run     │  │  │ Lifecycle: persists across runs │    │    │
│  │  └─────────────────┘  │  └──────────────────────────────────┘    │    │
│  └───────────────────────┼──────────────────────────────────────────┘    │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  AgentLens  │
                    │   Proxy     │
                    │ + Guards    │  ← Circuit breaker
                    │ + Traces    │  ← Observability
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  LLM API    │
                    │ (Claude /   │
                    │  Azure /    │
                    │  any)       │
                    └─────────────┘
```

### Agent Definitions (PydanticAI)

Each agent is a `PydanticAI Agent[DepsType, OutputType]` — typed, validated, with tools:

| Agent | Output Type | Tools | Deps |
|-------|-----------|-------|------|
| Spec Interpreter | `SpecInterpretation` (rules + ambiguities) | — | Spec YAML |
| Derivation Coder | `DerivationCode` (variable, code, approach) | `inspect_data`, `execute_code` | DataFrame, DerivationRule |
| QC Programmer | `DerivationCode` (same type, isolated context) | `inspect_data`, `execute_code` | DataFrame, DerivationRule |
| Debugger | `DebugAnalysis` (root cause, fix, verdict) | — (single-turn analysis) | Both implementations, divergent summary |
| Auditor | `AuditSummary` (stats, summary, recommendations) | — (single-turn summarization) | DAG metadata, provenance |

All agents share the same LLM gateway (`OpenAIChatModel` pointing to AgentLens proxy). The orchestrator dispatches them as independent async tasks.

## YAML-Driven Pipeline Engine

The orchestration sequence is **not hardcoded** — it's defined in YAML pipeline configs (`config/pipelines/*.yaml`) and executed by a `PipelineInterpreter`. This enables per-study customization without code changes.

### Composition Primitives

| StepType | What It Does | Example |
|----------|-------------|---------|
| `agent` | Run a single PydanticAI agent | `auditor` |
| `builtin` | Run a non-LLM Python function | `build_dag`, `export_adam` |
| `gather` | Run N agents in parallel | `coder + qc_programmer` |
| `parallel_map` | Map sub-steps over DAG layers | Variable derivation |
| `hitl_gate` | Pause for human approval | Review gate |

### Pipeline Configs

| Config | Steps | HITL Gates | Use Case |
|--------|-------|-----------|----------|
| `clinical_derivation.yaml` | 6 | 1 | Standard flow (default) |
| `express.yaml` | 4 | 0 | Rapid prototyping |
| `enterprise.yaml` | 8 | 3 | 21 CFR Part 11 compliance |

### Pipeline Interpreter

```
PipelineInterpreter.run()
  │
  ├── topological_sort(steps)        ← Kahn's algorithm, cycle detection
  │
  └── for step in sorted_steps:
        ├── STEP_EXECUTOR_REGISTRY[step.type].execute(step, ctx)
        └── PipelineFSM.advance(step.id)
```

The `PipelineFSM` auto-generates states from step IDs — no manual FSM maintenance.

See [docs/COMPOSITION_LAYER.md](docs/COMPOSITION_LAYER.md) for the full justification of building this composition layer on top of PydanticAI, including comparisons with CrewAI, LangGraph, Prefect, and Temporal.

## Data Security Architecture — Dual-Dataset Pattern

### The Problem

Clinical trial data (SDTM) contains patient-level information — USUBJID, age, sex, treatment dates, lab values. Even de-identified (pseudonymized), this data is regulated:
- **GDPR** (Sanofi is French) treats pseudonymized data as personal data
- **21 CFR Part 11** requires controlled access to electronic records
- **Sanofi data governance** likely prohibits sending patient-level data to external LLM APIs

If an agent sends `df.head()` in a prompt, patient rows leave the security perimeter. This is a compliance violation regardless of de-identification.

### The Solution: Agents Never See Patient Data

Agents need to understand the **shape** of data to write correct code — not the data itself. We enforce this with a dual-dataset architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Data Security Boundary                        │
│                                                                  │
│  ┌──────────────────┐         ┌──────────────────────────────┐  │
│  │ Real SDTM Data   │         │ Synthetic Reference Dataset  │  │
│  │ (patient-level)  │         │ (same schema, fake values)   │  │
│  │                  │         │                              │  │
│  │ • Never sent to  │         │ • Included in LLM prompts   │  │
│  │   LLM prompts    │         │ • 10-20 rows, realistic     │  │
│  │ • Only accessed   │         │   ranges                    │  │
│  │   by local tools │         │ • Committable to git         │  │
│  │ • Stays inside   │         │ • Generated from schema      │  │
│  │   the container  │         │   programmatically           │  │
│  └────────┬─────────┘         └──────────────┬───────────────┘  │
│           │                                  │                  │
│     ┌─────▼──────────────┐            ┌──────▼───────────┐      │
│     │ Tools              │            │ Agent Prompts    │      │
│     │ (execute locally)  │            │ (sent to LLM)    │      │
│     │                    │            │                  │      │
│     │ • execute_code:    │            │ • Schema info    │      │
│     │   runs pandas on   │            │ • Synthetic rows │      │
│     │   real data        │            │ • Derivation rule│      │
│     │ • inspect_data:    │            │                  │      │
│     │   returns schema + │            │ Never contains:  │      │
│     │   aggregates ONLY  │            │ • Real USUBJID   │      │
│     │                    │            │ • Real dates     │      │
│     │ Returns to LLM:    │            │ • Real lab values│      │
│     │ • null counts      │            │ • Any patient row│      │
│     │ • value ranges     │            │                  │      │
│     │ • pass/fail        │            │                  │      │
│     │ • error messages   │            │                  │      │
│     └────────────────────┘            └──────────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### What Each Agent Sees

| Agent | In prompt (→ LLM) | In tool results (→ LLM) | Accesses real data? |
|-------|-------------------|------------------------|-------------------|
| Spec Interpreter | Spec YAML + schema metadata | — | No |
| Derivation Coder | Schema + synthetic sample + rule | Aggregate stats (null count, value distribution, pass/fail) | Via tools only |
| QC Programmer | Schema + synthetic sample + rule | Same as Coder | Via tools only |
| Debugger | Divergent row INDICES + derived values | Diff analysis (which step diverged) | Via tools only |
| Auditor | DAG metadata, provenance | — | No |

### The `inspect_data` Tool Is the Security Gate

The `inspect_data` tool is the **only path** from real data to the LLM. It returns:
- Column names and dtypes
- Null counts per column
- Value ranges (min/max for numerics, unique values for categoricals)
- Row count

It **never returns**: raw rows, individual patient values, or USUBJID-level data.

The `execute_code` tool runs generated code on real data but returns only stdout (which we control — aggregate stats, not `print(df)`). A guard rule can block any response that contains patterns matching patient identifiers.

### Deployment Tiers

| Tier | LLM Location | Data Protection | Use Case |
|------|-------------|----------------|----------|
| **Prototype** | External Claude API | Only public CDISC pilot data + synthetic reference in prompts | Our demo |
| **Team deployment** | Azure OpenAI in Sanofi VNet (private endpoint) | LLM calls never leave network. Dual-dataset as defense-in-depth | Internal use |
| **Sovereign** | Self-hosted LLM on Sanofi infrastructure | Maximum control. Dual-dataset still applies (least-privilege) | Regulated studies |

### Why This Is Not Just a Demo Constraint

The dual-dataset pattern is the **correct production architecture** for pharma, not a workaround:
- **Least privilege:** agents don't need what they don't need. Code generation requires understanding structure, not content.
- **Defense in depth:** even if the LLM is inside the VNet, minimizing data exposure reduces blast radius of any breach.
- **Audit-friendly:** regulators can verify that no patient data flows to external services by inspecting prompts in the trace log (AgentLens captures every prompt).
- **Model-agnostic:** if Sanofi switches from Azure OpenAI to an internal model, the data architecture doesn't change.

## Transformation Spec — The Engine's Interface Contract

The derivation engine is **study-agnostic**. It doesn't know about CDISC, ADaM, or any specific therapeutic area. What it knows:
- A source dataset (any DataFrame)
- A transformation spec (YAML describing what to derive)
- A DAG of dependencies (built automatically from the spec)

The spec is the interface between clinical teams (who know the science) and the engine (which knows how to generate, verify, and audit code). Same engine, different YAML = different study. This is the §11A Platform Thinking answer.

### Spec → Engine → Output

```
specs/study_a.yaml + data/study_a/  →  Engine  →  Derived dataset + Audit trail
specs/study_b.yaml + data/study_b/  →  Engine  →  Derived dataset + Audit trail
         ↑                                ↑
   Study-specific                  Study-agnostic
   (written by biostat team)       (same code for all studies)
```

### Spec Structure (summary)

```yaml
study: cdiscpilot01                    # Study identifier
source:
  format: xpt                          # xpt, csv, parquet
  path: data/sdtm/cdiscpilot01
  domains: [dm, ex, ds]                # Source data files
  primary_key: USUBJID

derivations:
  - variable: AGE_GROUP                # What to derive
    source_columns: [AGE]              # From what (source OR derived)
    logic: "Categorize into ..."       # Plain English rule
    output_type: str                   # Expected dtype
    allowed_values: ["<18","18-64",">=65"]  # Validation constraint

  - variable: RISK_GROUP
    source_columns: [AGE_GROUP, SAFFL] # ← depends on derived variables
    logic: "High if >=65 and safety pop..."
    output_type: str

validation:
  ground_truth:
    path: data/adam/cdiscpilot01/adsl.xpt  # Compare against known-good
    key: USUBJID
```

The engine reads `source_columns` and automatically detects dependencies: if `RISK_GROUP` lists `AGE_GROUP` (a derived variable), the DAG ensures AGE_GROUP is computed first.

### Build Order: Engine First, Data Second

1. **Define the spec format** (done — see `specs/TEMPLATE.md`)
2. **Build the engine** against the spec interface, test with simple mock data (`specs/simple_mock.yaml`)
3. **Write the CDISC spec** and validate with real data (`specs/cdiscpilot01_adsl.yaml`)

This order ensures the engine is genuinely spec-agnostic — we don't accidentally hardcode CDISC assumptions.

Full spec format reference: [`specs/TEMPLATE.md`](specs/TEMPLATE.md)

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Language | Python 3.13+ | Industry standard for data science + ML, typing maturity |
| Agent framework | PydanticAI | Type-safe agents, structured output, true async, dependency injection (validated by prototype) |
| LLM | Claude API (OpenAI-compatible endpoint) | Via AgentLens mailbox — model-agnostic, swappable |
| Observability | AgentLens | OTel-based tracing, deterministic evaluators, audit export |
| Data processing | pandas + pyreadstat | XPT file support, DataFrame operations |
| DAG engine | networkx | Graph construction, topological sort, cycle detection |
| UI | Streamlit | Rapid HITL prototyping, approval workflows |
| Database | PostgreSQL (SQLite for unit tests) | Long-term memory, workflow state, audit trail (ACID) |
| Package manager | uv | Fast, deterministic, lockfile-based |
| Testing | pytest | Standard, mature, good fixture support |
| Linting | ruff | Fast, comprehensive, replaces flake8+isort+black |
| Type checking | pyright (strict) | Catches bugs before runtime, enforces contracts |
| CI | GitHub Actions | Lint + typecheck + test on every push |

## Production Architecture — Deployment Scenarios

### Context

Sanofi has global R&D teams across NJ, Paris, and other sites. A production system must support multiple concurrent researchers running derivations across different studies. Below are two deployment scenarios: one we build and test, one we architect toward.

### Scenario A: Docker Compose (Build This, Test Locally)

Service-separated architecture that runs locally and migrates directly to Kubernetes. Each concern is its own container, communicating over an internal network. AgentLens mailbox is exposed for external LLM connection (real API or development brain).

```
                         ┌──────────────────────┐
                         │      Browser         │
                         └──────────┬───────────┘
                                    │
┌─ docker-compose.yml ──────────────┼──────────────────────────────────────┐
│                                   │                                      │
│  ┌────────────────┐    ┌─────────▼──────────┐    ┌────────────────────┐ │
│  │    nginx        │───►│   Streamlit UI     │    │   Grafana/Loki    │ │
│  │  (reverse proxy │    │   (HITL pages)     │    │   (log viewer)    │ │
│  │   + load bal.)  │    │   Port 8501        │    │   Port 3000       │ │
│  └────────────────┘    └─────────┬───────────┘    └────────▲──────────┘ │
│                                  │                         │            │
│                       ┌──────────▼───────────┐     loguru  │            │
│                       │   FastAPI Backend    │─────────────┘            │
│                       │   (HITL API +        │                          │
│                       │    Orchestration     │                          │
│                       │    Engine)           │                          │
│                       │   Port 8000          │                          │
│                       └────┬─────────┬───────┘                          │
│                            │         │                                  │
│                   ┌────────▼───┐ ┌───▼────────────┐                    │
│                   │ PostgreSQL │ │  AgentLens      │                    │
│                   │ (state +   │ │  Proxy          │                    │
│                   │  memory +  │ │  + Guards       │                    │
│                   │  audit)    │ │  Port 8650      │◄──── exposed ────── │
│                   │ Port 5432  │ │  (mailbox or    │     (LLM / brain)  │
│                   └────────────┘ │   proxy mode)   │                    │
│                                  └────────┬────────┘                   │
│                                           │ proxy mode only            │
└───────────────────────────────────────────┼────────────────────────────┘
                                            │
                                   ┌────────▼────────┐
                                   │  LLM API        │  ← External service
                                   │  (Claude /      │     (not in compose)
                                   │   Azure OpenAI) │
                                   └─────────────────┘
```

**Services (6 containers):**

| Container | Image | Purpose | Port |
|-----------|-------|---------|------|
| `nginx` | nginx:alpine | Reverse proxy, load balancer, TLS termination | 80/443 |
| `ui` | Custom (Streamlit) | HITL approval pages, DAG visualization, audit viewer | 8501 |
| `backend` | Custom (FastAPI) | HITL API + orchestration engine + agent dispatch | 8000 |
| `db` | postgres:16 | Workflow state, long-term memory, audit trail (ACID) | 5432 |
| `agentlens` | Custom (AgentLens) | LLM proxy + guards + tracing | 8650 |
| `logs` | grafana/loki + grafana | Log aggregation + visualization | 3000 |

| Pros | Cons |
|------|------|
| Service separation = production-like topology | More complex than single process |
| PostgreSQL from day one (no SQLite→PG migration) | Requires Docker on dev machine |
| AgentLens in own container = independent scaling | 6 containers to manage |
| Grafana/Loki for log visualization during demo | |
| `docker compose up` to start everything | |
| Direct migration path to K8s (same images) | |
| AgentLens mailbox exposed for dev brain | |
| Nginx enables multiple backend replicas | |

**Verdict:** Our prototype AND our demo. Testable locally, impressive to present, direct path to production.

**Key design property:** The backend container is stateless — all state lives in PostgreSQL. This means you can run N backend replicas behind nginx for horizontal scaling. Same images deploy to Kubernetes with a Helm chart.

### Scenario B: Kubernetes (Enterprise Target)

Same container images as Scenario A, deployed to Azure Kubernetes Service with auto-scaling, proper networking, and enterprise integrations.

```
┌────────────────┐     ┌──────────────────────────────────────────────────┐
│   Browser      │     │              Azure Kubernetes Service             │
│                │     │                                                   │
│  ┌──────────┐  │     │  ┌───────────┐   ┌────────────────────────────┐  │
│  │ React /  │──┼─────┼─►│ Ingress   │──►│ Backend Pods (N replicas)  │  │
│  │ Streamlit│  │     │  │ Controller│   │ (FastAPI + Orchestration)  │  │
│  │          │  │     │  └───────────┘   └──────────┬─────────────────┘  │
│  └──────────┘  │     │                             │                    │
└────────────────┘     │       ┌─────────────────────┼──────────┐         │
                       │       │                     │          │         │
                       │  ┌────▼─────┐  ┌────────────▼───┐  ┌──▼──────┐  │
                       │  │PostgreSQL│  │ AgentLens Pods │  │ Grafana │  │
                       │  │ (managed │  │ (N replicas,   │  │ + Loki  │  │
                       │  │  or PaaS)│  │  guards.yaml   │  │         │  │
                       │  └──────────┘  │  per study)    │  └─────────┘  │
                       │                └───────┬────────┘               │
                       │                        │                        │
                       │          ┌─────────────▼────────────────┐       │
                       │          │  LLM Gateway (Envoy / custom)│       │
                       │          │  rate limit, routing,        │       │
                       │          │  fallback, model selection   │       │
                       │          └─────────────┬────────────────┘       │
                       └────────────────────────┼────────────────────────┘
                                                │
                          ┌─────────────────────▼───────────────────┐
                          │  LLM Providers (Azure OpenAI /          │
                          │  Anthropic / Sanofi internal fine-tuned) │
                          └─────────────────────────────────────────┘
```

**What changes from Scenario A to B:**

| Concern | Scenario A (Docker Compose) | Scenario B (Kubernetes) |
|---------|----------------------------|------------------------|
| Scaling | Manual (`replicas: N` in compose) | Auto-scaling (HPA on CPU/request count) |
| Database | PostgreSQL container | Azure Database for PostgreSQL (managed PaaS) |
| Networking | Docker internal network | Azure VNet + private endpoints |
| TLS | nginx self-signed or Let's Encrypt | Azure Application Gateway + cert management |
| Secrets | `.env` file | Azure Key Vault |
| Monitoring | Grafana/Loki container | Azure Monitor + Grafana Cloud |
| Guard configs | Single `guards.yaml` | ConfigMap per study (different compliance levels) |
| CI/CD | `docker compose build && push` | Helm chart + ArgoCD / Azure DevOps |

**What stays the same:** Container images, API contracts, database schema, agent definitions. The migration is a deployment concern, not a code change.

| Pros | Cons |
|------|------|
| Horizontal auto-scaling | Requires K8s expertise |
| Real multi-tenancy (namespace per study) | Higher infrastructure cost |
| Managed PostgreSQL (backups, HA) | More operational complexity |
| Guard configs per study via ConfigMaps | |
| VNet isolation for data security | |

**Verdict:** Enterprise target. Same images as Scenario A, different orchestration layer (K8s instead of Docker Compose).

### Recommended Path

**Build Scenario A (Docker Compose) as the deliverable.** It is testable, demonstrable, and architecturally identical to Scenario B:
- Same container images deploy to both Docker Compose and Kubernetes
- PostgreSQL from day one — no SQLite migration needed
- Backend is stateless — N replicas behind nginx work in Compose, behind Ingress in K8s
- AgentLens mailbox exposed for development (external brain), proxy mode for production
- Guard configs are per-study even in Compose (mount different `guards.yaml`)
- Grafana/Loki included for demo — shows observability is real, not just documented

## Project Structure

```
homework/
├── CLAUDE.md
├── ARCHITECTURE.md            # This file
├── decisions.md
├── pyproject.toml
├── uv.lock
├── .importlinter              # Layer contracts enforced by import-linter
├── .pre-commit-config.yaml    # 18 pre-push hooks (ruff, pyright, radon, custom arch checks)
├── .github/workflows/ci.yml
├── docs/
│   ├── homework.md            # Original assignment
│   ├── REQUIREMENTS.md        # Problem framing & decisions
│   ├── design.md              # Deliverable design document (source of truth)
│   ├── design.docx            # Word export for panel review (generated via pandoc)
│   └── GAP_ANALYSIS.md        # Code review gap tracking
├── data/
│   ├── sdtm/cdiscpilot01/     # SDTM input (XPT)
│   └── adam/cdiscpilot01/     # ADaM ground truth (XPT)
├── specs/                     # Transformation specs (YAML: simple_mock, adsl_cdiscpilot01)
├── config/
│   ├── README.md
│   ├── guards.yaml            # AgentLens guard rules (design artifact, Phase 16.5)
│   ├── agents/                # Per-agent YAML (factory + registry wire these up)
│   │   ├── coder.yaml
│   │   ├── qc_programmer.yaml
│   │   ├── debugger.yaml
│   │   ├── auditor.yaml
│   │   └── spec_interpreter.yaml
│   └── pipelines/             # YAML-driven orchestration definitions
│       ├── clinical_derivation.yaml  # Standard 8-step flow (incl. ground_truth_check, save_patterns)
│       ├── express.yaml              # 4-step rapid prototyping (no HITL, no QC)
│       └── enterprise.yaml           # 9-step enterprise flow (3 HITL gates for 21 CFR Part 11)
├── src/
│   ├── __init__.py
│   ├── factory.py                 # DI factory — constructs PipelineContext with repos + session
│   ├── config/                    # Infrastructure configuration
│   │   ├── __init__.py
│   │   ├── llm_gateway.py         # Single point of LLM model construction (AgentLens proxy)
│   │   ├── logging.py             # loguru configuration
│   │   └── settings.py            # pydantic-settings BaseSettings
│   ├── domain/                    # Pure domain (no framework deps above networkx/pandas/pyreadstat)
│   │   ├── __init__.py
│   │   ├── models.py              # DerivationRule, DAGNode, DerivationRunResult, Transformation/SourceConfig, ValidationConfig
│   │   ├── enums.py               # AgentName, AuditAction, DerivationStatus, OutputDType, QCVerdict, ConfidenceLevel, WorkflowStep, …
│   │   ├── exceptions.py          # CDDEError, DerivationError, NotFoundError, WorkflowRejectedError, WorkflowStateError
│   │   ├── dag.py                 # DAG construction, topological sort, apply_run_result, layers
│   │   ├── ground_truth.py        # GroundTruthReport + VariableGroundTruthResult (Phase 16.4)
│   │   ├── pipeline_models.py     # StepType, StepDefinition, PipelineDefinition, load_pipeline
│   │   ├── spec_parser.py         # YAML spec → DerivationRule objects
│   │   ├── executor.py            # Safe derivation execution + compare_results helper
│   │   ├── source_loader.py       # CSV/XPT file loading, left-join merge on primary key
│   │   ├── synthetic.py           # Privacy-safe synthetic data generation
│   │   └── workflow_models.py     # WorkflowState, WorkflowResult
│   ├── agents/                    # PydanticAI agent wiring (YAML-configured)
│   │   ├── __init__.py
│   │   ├── deps.py                # CoderDeps / AuditorDeps / DebuggerDeps / SpecInterpreterDeps
│   │   ├── factory.py             # load_agent(path) — builds Agent from YAML + TOOL_MAP
│   │   ├── registry.py            # OUTPUT_TYPE_MAP, DEPS_TYPE_MAP, TOOL_MAP
│   │   ├── types.py               # DerivationCode, DebugAnalysis, SpecInterpretation
│   │   └── tools/
│   │       ├── __init__.py        # Re-exports inspect_data, execute_code, query_patterns
│   │       ├── sandbox.py         # Safe builtins, blocked tokens, namespace builder
│   │       ├── inspect_data.py    # Data inspection tool (schema, nulls, ranges)
│   │       ├── execute_code.py    # Sandboxed code execution tool
│   │       ├── query_patterns.py  # Long-term memory tool (Phase 16.1)
│   │       └── tracing.py         # @traced_tool decorator for observability
│   ├── engine/                    # Orchestration layer (YAML-driven pipeline interpreter)
│   │   ├── __init__.py
│   │   ├── pipeline_interpreter.py   # Topological sort (Kahn) + step dispatch loop
│   │   ├── pipeline_fsm.py           # Lightweight state tracker (states derived from step IDs)
│   │   ├── pipeline_context.py       # Shared mutable state: dag, derived_df, spec, repos (DI), rejection flags
│   │   ├── step_executors.py         # Agent / Builtin / Gather / ParallelMap / HITLGate executors
│   │   ├── step_builtins.py          # parse_spec, build_dag, export_adam, save_patterns, compare_ground_truth
│   │   ├── derivation_runner.py      # Per-variable coder+QC+verify+debug loop
│   │   └── debug_runner.py           # Debug agent dispatch + apply_series_to_df helper
│   ├── verification/              # QC / double programming (independent from agents)
│   │   ├── __init__.py
│   │   └── comparator.py
│   ├── audit/                     # Traceability
│   │   ├── __init__.py
│   │   └── trail.py
│   ├── persistence/               # SQLAlchemy async data access layer
│   │   ├── __init__.py            # Re-exports all repos
│   │   ├── database.py            # Async engine + session factory
│   │   ├── orm_models.py          # 4 tables: patterns, feedback, qc_history, workflow_states
│   │   ├── base_repo.py           # BaseRepository (execute/flush/commit with error wrapping)
│   │   ├── pattern_repo.py        # PatternRepository — store/query_by_type (LTM, Phase 16.1)
│   │   ├── feedback_repo.py       # FeedbackRepository — HITL approve/reject feedback (Phase 16.2)
│   │   ├── qc_history_repo.py     # QCHistoryRepository — verdict timeline
│   │   └── workflow_state_repo.py # WorkflowStateRepository — per-step checkpoints (Phase 15)
│   └── api/                       # FastAPI REST + FastMCP 3.0 server
│       ├── __init__.py
│       ├── app.py                 # App factory, lifespan, router registration
│       ├── dependencies.py        # WorkflowManagerDep, AuditorDep
│       ├── mcp_server.py          # FastMCP tools: run_workflow, get_workflow_status, get_workflow_result
│       ├── schemas.py             # All request/response DTOs
│       ├── workflow_manager.py    # Workflow lifecycle coordinator (contexts, sessions, events)
│       ├── workflow_hitl.py       # Approve/reject/feedback helpers (Phase 16.2b, extracted for size)
│       ├── workflow_lifecycle.py  # Start/cleanup helpers (extracted in commit 3a8ee62)
│       ├── workflow_serializer.py # Domain → DTO conversion
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── workflows.py       # Workflow CRUD, status, dag, audit, data, pipeline, ground_truth (Phase 16.4)
│       │   ├── hitl.py            # /approve /reject /variables/{var}/override (Phase 16.2b)
│       │   ├── data.py            # Derived dataset preview endpoint
│       │   ├── pipeline.py        # /pipeline — current pipeline definition
│       │   └── specs.py           # Spec listing + content
│       └── services/
│           ├── __init__.py
│           └── override_service.py  # Variable override flow — validates, executes, persists (Phase 16.2b)
├── frontend/                      # Vite + React 18 + TypeScript SPA
│   ├── package.json
│   ├── pnpm-lock.yaml             # Committed in Phase 16.3 for reproducible builds
│   ├── vitest.config.ts
│   ├── tsconfig.app.json
│   └── src/
│       ├── main.tsx
│       ├── pages/
│       │   ├── DashboardPage.tsx
│       │   └── WorkflowDetailPage.tsx
│       ├── components/
│       │   ├── ui/                # shadcn primitives (incl. textarea.tsx added in Phase 16.3a)
│       │   ├── WorkflowHeader.tsx
│       │   ├── WorkflowTabs.tsx
│       │   ├── CodePanel.tsx
│       │   ├── DAGView.tsx
│       │   ├── PipelineView.tsx
│       │   ├── RejectDialog.tsx          # Phase 16.3b
│       │   ├── ApprovalDialog.tsx        # Phase 16.3b
│       │   ├── VariableApprovalList.tsx  # Phase 16.3b
│       │   └── CodeEditorDialog.tsx      # Phase 16.3b
│       ├── hooks/useWorkflows.ts         # TanStack Query hooks (incl. HITL mutations)
│       ├── lib/api.ts                    # Typed API client object + fetchJson<T> helper
│       └── types/api.ts                  # TypeScript interfaces mirroring Pydantic schemas
├── scripts/                       # Helper scripts (non-pipeline)
│   ├── README.md
│   ├── download_data.py           # CDISC pilot data fetcher
│   ├── validate_adam.py           # Compare derived CSV vs ground truth
│   ├── mailbox_simple_mock.py     # Deterministic mock responder for simple_mock spec
│   ├── mailbox_cdisc.py           # Deterministic mock responder for adsl_cdiscpilot01 spec
│   ├── mcp_run_cdisc.py           # End-to-end CDISC workflow driver via MCP
│   └── mcp_test_checkpoint.py     # Per-step checkpoint verification via MCP
├── tools/
│   └── pre_commit_checks/         # 10 custom arch checks (domain purity, enum discipline, …)
├── tests/
│   ├── conftest.py
│   ├── unit/                      # Domain, agents, engine, API, persistence, FSM unit tests
│   └── integration/
│       ├── test_workflow.py
│       ├── test_cdisc.py
│       ├── test_pipeline_equivalence.py
│       ├── test_long_term_memory.py         # Phase 16.1
│       ├── test_hitl_flows.py               # Phase 16.2b
│       └── test_ground_truth_runtime.py     # Phase 16.4
└── presentation/                  # Slide deck + code review + diagrams
```

## Layer Responsibilities

### config/ — Infrastructure Configuration
- **Does:** Configure LLM gateway, logging, shared constants
- **Must NOT:** Contain business logic or domain models
- **Depends on:** Nothing (leaf layer)

### domain/ — Pure Domain Logic
- **Does:** Define data models, build DAGs, parse specs, execute derivation functions
- **Must NOT:** Import PydanticAI, Streamlit, SQLAlchemy, or any infrastructure package
- **Pattern:** All derivations are pure functions `(DataFrame, params) -> Series`

### agents/ — AI Agent Definitions
- **Does:** Define PydanticAI agents, their roles, tools, and output types
- **Must NOT:** Execute workflows, manage state, or access the database directly
- **Depends on:** domain/

### engine/ — Orchestration
- **Does:** Run the YAML-driven `PipelineInterpreter`, dispatch steps via `STEP_EXECUTOR_REGISTRY`, run derivations in DAG-layer order, coordinate persistence and audit via DI-injected repositories on `PipelineContext`.
- **Must NOT:** Define domain models, render UI, or import `sqlalchemy` directly — the `check_raw_sql_in_engine` pre-push hook enforces this.
- **Depends on:** domain/, agents/, verification/, audit/. Uses `PatternRepository` and `QCHistoryRepository` only via TYPE_CHECKING annotations — the repos are constructed in `src/factory.py` (outside the engine layer) and injected via `PipelineContext`.

### verification/ — QC & Double Programming
- **Does:** Compare primary vs QC outputs, generate discrepancy reports
- **Must NOT:** Generate derivations (that's the agents' job)
- **Depends on:** domain/

### audit/ — Traceability
- **Does:** Record audit trail, export lineage, generate reports
- **Must NOT:** Make derivation decisions
- **Depends on:** domain/

### persistence/ — Database Layer
- **Does:** Encapsulate all DB queries; store/retrieve patterns, feedback, QC history, workflow state. All repos derive from `BaseRepository` and wrap `OperationalError` / `IntegrityError` as `RepositoryError`. `BaseRepository.commit()` is the single commit point used by engine builtins (e.g. `save_patterns`).
- **Must NOT:** Contain business logic or domain decisions
- **Depends on:** domain/ (for Pydantic models returned to callers)

### api/ — FastAPI REST + FastMCP Server
- **Does:** Expose the pipeline over HTTP (`routers/workflows.py`, `routers/hitl.py`, `routers/data.py`, `routers/pipeline.py`, `routers/specs.py`) and as MCP tools (`mcp_server.py`). Owns the workflow lifecycle via `WorkflowManager` (contexts + sessions + approval events). Service-layer helpers (`services/override_service.py`) handle multi-step business logic; the `api-no-persistence` import-linter contract is relaxed here via documented `ignore_imports` so the manager can own the session lifecycle.
- **Must NOT:** Contain derivation logic or direct LLM calls — those live in the engine and agents layers.
- **Depends on:** everything (top of the stack).

## Data Layer — Database Schema

The engine runs against SQLite in development (`cdde.db` in the repo root) and is designed to swap to PostgreSQL in production by changing `DATABASE_URL` — nothing else changes. All four tables are defined in `src/persistence/orm_models.py` using SQLAlchemy 2.0 `Mapped[]` style.

### `patterns` — Approved derivation cache (Phase 16.1)

Populated by the `save_patterns` builtin after the `human_review` HITL gate. Queried by the `query_patterns` PydanticAI tool so the coder agent can adapt prior approved code instead of regenerating from scratch. **This is the long-term memory loop**: every human-approved derivation feeds future runs.

| Column | Type | Index | Purpose |
|---|---|---|---|
| `id` | `int` | PK | Auto-increment |
| `variable_type` | `varchar(100)` | ✅ (btree) | Variable name the pattern solves for (lookup key) |
| `spec_logic` | `text` | — | Original rule logic from the spec |
| `approved_code` | `text` | — | The pandas expression the human approved |
| `study` | `varchar(100)` | — | Study identifier (provenance) |
| `approach` | `varchar(200)` | — | Short description of the coder's strategy |
| `created_at` | `timestamp with tz` | — | UTC (datetime-aware via `check_datetime_patterns`) |

Populated by: `_builtin_save_patterns` (`src/engine/step_builtins.py`)
Read by: `query_patterns` tool (`src/agents/tools/query_patterns.py`)

### `feedback` — HITL feedback capture (Phase 16.2)

Every human action at a HITL gate (approve, reject, override) writes here. Closes the feedback loop between reviewer intent and downstream agent behavior; future phases can use this for fine-tuning datasets or for surfacing "commonly rejected variables" on the dashboard.

| Column | Type | Index | Purpose |
|---|---|---|---|
| `id` | `int` | PK | Auto-increment |
| `variable` | `varchar(100)` | ✅ (btree) | Variable the feedback applies to (`""` for workflow-level reject) |
| `feedback` | `text` | — | Free-text reviewer note or rejection reason |
| `action_taken` | `varchar(200)` | — | `"approved"` / `"rejected"` / `"overridden"` |
| `study` | `varchar(100)` | — | Study identifier (provenance) |
| `created_at` | `timestamp with tz` | — | UTC |

Populated by: `approve_with_feedback_impl` + `reject_workflow_impl` (`src/api/workflow_hitl.py`), `override_variable` (`src/api/services/override_service.py`)

### `qc_history` — QC verdict timeline (Phase 16.1)

Companion to `patterns` — stores the coder-vs-QC comparison verdict for every approved derivation. Enables trend analysis ("how often does the QC programmer match the coder?") and drives the `qc_history_repo.get_stats()` helper used in tests.

| Column | Type | Index | Purpose |
|---|---|---|---|
| `id` | `int` | PK | Auto-increment |
| `variable` | `varchar(100)` | ✅ (btree) | Variable the verdict applies to |
| `verdict` | `varchar(50)` | — | `QCVerdict` enum value (`match` / `mismatch`) |
| `coder_approach` | `varchar(200)` | — | Coder's strategy label |
| `qc_approach` | `varchar(200)` | — | QC programmer's (different) strategy label |
| `study` | `varchar(100)` | — | Study identifier (provenance) |
| `created_at` | `timestamp with tz` | — | UTC |

Populated by: `_builtin_save_patterns` (`src/engine/step_builtins.py`)
Read by: `QCHistoryRepository.get_stats()` (tests + future dashboard)

### `workflow_states` — Per-step checkpoint (Phase 15)

Powers the restart-from-last-checkpoint story. After every step completes, `run_with_checkpoint` upserts the full `PipelineContext` JSON snapshot keyed by `workflow_id`, and the FSM state name. On restart the row is rehydrated and the interpreter resumes from the next step. `workflow_id` has a unique index so upserts are fast and consistent.

| Column | Type | Index | Purpose |
|---|---|---|---|
| `id` | `int` | PK | Auto-increment |
| `workflow_id` | `varchar(20)` | ✅ unique | Workflow identifier (short UUID, one row per workflow) |
| `state_json` | `text` | — | Serialized `PipelineContext` snapshot |
| `fsm_state` | `varchar(50)` | — | Current FSM state name (debugging / observability) |
| `updated_at` | `timestamp with tz` | — | Checkpoint timestamp (UTC) |

Populated by: `run_with_checkpoint` in the engine, called after every step completion
Read by: workflow restart flow in `WorkflowManager`, the checkpoint observability script `scripts/mcp_test_checkpoint.py`

### Retention & migration notes

- **Local dev:** SQLite file at `./cdde.db` — zero setup, committed to `.gitignore`.
- **Production target:** PostgreSQL — only the `DATABASE_URL` changes. `src/persistence/database.py` uses `create_async_engine`, which accepts either `sqlite+aiosqlite://` or `postgresql+asyncpg://`.
- **Migrations:** Alembic is the intended tool (not wired in yet — homework scope). Schema changes would land in `alembic/versions/` and be applied by the container at startup.
- **Retention:** `patterns` and `qc_history` are append-only — no deletion. `workflow_states` is upsert-by-workflow-id (one row per run; resuming overwrites). `feedback` is append-only. For a production deployment with long-running workflows, `workflow_states` rows older than N days could be archived to a cold-storage bucket; this is out of scope for the homework.

## Data Flow — Typical Derivation Lifecycle

```
1. User uploads/selects SDTM dataset + transformation spec (YAML)
                           │
2. Spec Interpreter Agent  │  Parses spec, extracts rules, flags ambiguities
                           │  → Human reviews flagged ambiguities (HITL gate 1)
                           ▼
3. DAG Construction        │  Builds dependency graph from derivation rules
                           │  → Topological sort determines execution order
                           ▼
4. For each derivation     │  (in topological order):
   in DAG order:           │
                           │
   4a. Derivation Coder    │  Generates Python code for this variable
       Agent               │
                           │
   4b. QC Programmer       │  Independently generates alternative implementation
       Agent               │  (NO access to 4a's code)
                           │
   4c. Comparator          │  Runs both implementations, compares outputs
                           │  → If match: auto-approve
                           │  → If mismatch: Debugger Agent investigates
                           │     → Human reviews discrepancy (HITL gate 2)
                           ▼
5. Human reviews final     │  Derived dataset + QC report (HITL gate 3)
   outputs                 │
                           ▼
6. Auditor Agent           │  Generates full audit trail:
                           │  → Source-to-output lineage (enhanced DAG)
                           │  → All agent actions with timestamps
                           │  → Human interventions logged
                           │  → Export to JSON + HTML
                           ▼
7. Output: ADaM dataset + verification report + audit trail
```

## Key Domain Concepts

| Concept | Description |
|---------|-------------|
| **DerivationRule** | A single transformation: source variables → derived variable, with logic |
| **DerivationDAG** | Directed acyclic graph of DerivationRules, determines execution order |
| **DAGNode** | Enhanced node: rule + generated code + agent provenance + QC status + approval |
| **AuditRecord** | Immutable record: timestamp, agent, input hash, output hash, rule, QC result |
| **WorkflowState** | FSM tracking the current step in the derivation lifecycle |
| **ValidatedPattern** | Long-term memory entry: an approved derivation pattern reusable across studies |

## State Machine — Workflow

```
                    ┌──────────────┐
                    │   CREATED    │
                    └──────┬───────┘
                           │ upload spec + data
                    ┌──────▼───────┐
                    │  SPEC_REVIEW │◄──── Human edits spec
                    └──────┬───────┘
                           │ spec approved
                    ┌──────▼───────┐
                    │  DAG_BUILT   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
              ┌────►│  DERIVING    │◄───┐
              │     └──────┬───────┘    │
              │            │            │ next variable
              │     ┌──────▼───────┐    │
              │     │  VERIFYING   │────┘ (if QC pass)
              │     └──────┬───────┘
              │            │ QC mismatch
              │     ┌──────▼───────┐
              └─────│  DEBUGGING   │
             (retry)└──────────────┘
                           │ all variables done
                    ┌──────▼───────┐
                    │   REVIEW     │◄──── Human final approval
                    └──────┬───────┘
                           │ approved
                    ┌──────▼───────┐
                    │  AUDITING    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  COMPLETED   │
                    └──────────────┘
```

## Orchestration Patterns

| Pattern | Where Used | Description |
|---------|-----------|-------------|
| **Sequential** | Overall workflow | Steps proceed in order: spec → DAG → derive → verify → audit |
| **Fan-out / Fan-in** | Independent derivations | Variables with no mutual dependencies can be derived in parallel |
| **Concurrent + Compare** | Double programming | Primary Coder and QC Programmer run concurrently on same variable, outputs compared |
| **Retry with escalation** | QC mismatch | Debugger attempts fix → if still mismatched, escalate to human |
| **Gate (HITL)** | Spec review, QC disputes, final approval | Workflow pauses until human approves/edits |
