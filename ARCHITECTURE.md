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
├── .github/workflows/ci.yml
├── docs/
│   ├── homework.md            # Original assignment
│   ├── REQUIREMENTS.md        # Problem framing & decisions
│   └── design.md              # Deliverable design document
├── data/
│   ├── sdtm/cdiscpilot01/     # SDTM input (XPT)
│   └── adam/cdiscpilot01/     # ADaM ground truth (XPT)
├── specs/                     # Transformation specs (YAML)
├── src/
│   ├── __init__.py
│   ├── domain/                # Pure domain: models, DAG, spec parsing, code execution
│   │   ├── __init__.py
│   │   ├── models.py          # DerivationRule, DAGNode, AuditRecord, etc.
│   │   ├── dag.py             # DAG construction, topological sort
│   │   ├── spec_parser.py     # YAML spec → DerivationRule objects
│   │   └── executor.py        # Safe code execution + result comparison
│   ├── agents/                # PydanticAI agent definitions
│   │   ├── __init__.py
│   │   ├── tools.py           # Shared tools: inspect_data, execute_code
│   │   ├── spec_interpreter.py
│   │   ├── derivation_coder.py
│   │   ├── qc_programmer.py
│   │   ├── debugger.py
│   │   └── auditor.py
│   ├── engine/                # Orchestration layer
│   │   ├── __init__.py
│   │   ├── orchestrator.py    # Workflow FSM, agent dispatch
│   │   ├── llm_gateway.py     # LLM abstraction (AgentLens mailbox)
│   │   └── logging.py         # loguru configuration
│   ├── verification/          # QC / double programming
│   │   ├── __init__.py
│   │   └── comparator.py      # Compare primary vs QC outputs, AST similarity
│   ├── audit/                 # Traceability
│   │   ├── __init__.py
│   │   └── trail.py           # Audit trail management + JSON export
│   ├── memory/                # Short-term + long-term memory
│   │   ├── __init__.py
│   │   ├── short_term.py      # Workflow state (JSON per run)
│   │   └── long_term.py       # Validated patterns (SQLite)
│   └── ui/                    # Streamlit HITL
│       ├── __init__.py
│       ├── app.py             # Main entry point
│       └── pages/             # Streamlit multi-page
│           ├── 1_spec_review.py
│           ├── 2_derivation_review.py
│           ├── 3_qc_results.py
│           └── 4_audit_trail.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_dag.py
│   │   ├── test_spec_parser.py
│   │   ├── test_agents.py
│   │   ├── test_executor.py
│   │   ├── test_comparator.py
│   │   ├── test_orchestrator.py
│   │   ├── test_memory.py
│   │   └── test_audit.py
│   └── integration/
│       └── test_workflow.py
└── presentation/
```

## Layer Responsibilities

### domain/ — Pure Domain Logic
- **Does:** Define data models, build DAGs, parse specs, execute derivation functions
- **Must NOT:** Import PydanticAI, Streamlit, SQLite, or any infrastructure package
- **Pattern:** All derivations are pure functions `(DataFrame, params) -> Series`

### agents/ — AI Agent Definitions
- **Does:** Define PydanticAI agents, their roles, tools, and output types
- **Must NOT:** Execute workflows, manage state, or access the database directly
- **Depends on:** domain/

### engine/ — Orchestration
- **Does:** Run the workflow FSM, dispatch agents in DAG order, manage LLM calls, wire memory and audit
- **Must NOT:** Define domain models or render UI
- **Depends on:** domain/, agents/, memory/, audit/

### verification/ — QC & Double Programming
- **Does:** Compare primary vs QC outputs, generate discrepancy reports
- **Must NOT:** Generate derivations (that's the agents' job)
- **Depends on:** domain/

### audit/ — Traceability
- **Does:** Record audit trail, export lineage, generate reports
- **Must NOT:** Make derivation decisions
- **Depends on:** domain/

### memory/ — State Management
- **Does:** Persist workflow state (short-term) and validated patterns (long-term)
- **Must NOT:** Contain business logic
- **Depends on:** domain/

### ui/ — Human-in-the-Loop Interface
- **Does:** Render Streamlit pages, capture human approvals, display results
- **Must NOT:** Contain derivation logic or direct LLM calls
- **Depends on:** everything (top of the stack)

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
