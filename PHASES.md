# Release Phases — Feature Roadmap

## Current Release: Engine Core (Phases 1-4)

**Scope:** Spec-agnostic derivation engine with `simple_mock.yaml` test scenario.
**What it delivers:** Full pipeline from YAML spec → DAG → agents → double programming → audit trail, testable via AgentLens mailbox with mock CSV data.

| Phase | Title | Key Features | Status |
|-------|-------|-------------|--------|
| **1** | Project Setup + Domain | pyproject.toml, CI, domain models, DAG (networkx), spec parser (YAML→Pydantic), synthetic data generator, test fixtures, `simple_mock.yaml` | Planned |
| **2** | Agents + LLM Gateway | 5 PydanticAI agents, `inspect_data` tool (security gate), `execute_code` tool (sandboxed), LLM gateway (AgentLens proxy) | Planned |
| **3** | Orchestration + Verification | Workflow FSM, DAG-ordered executor, asyncio.gather fan-out, QC comparator, AST similarity check, Debugger retry loop | Planned |
| **4** | Memory + Audit + Integration | Short-term memory (JSON/run), long-term memory (SQLite), audit trail (append-only), end-to-end integration test | Planned |

---

## Future Phases (Scoped Out — To Be Planned)

### Phase 5: CDISC Pilot Data Scenario

**Scope:** Validate engine with real clinical trial data.

| Feature | Description | Depends On |
|---------|------------|-----------|
| CDISC spec file | `specs/cdiscpilot01_adsl.yaml` — real ADaM ADSL derivations (AGE_GROUP, TREATMENT_DURATION, SAFFL, ITTFL, PPROTFL, RISK_GROUP) | Phase 1-4 |
| XPT file support | Add `pyreadstat` to load SAS Transport (.xpt) files in `spec_parser.py` | Phase 1 |
| Ground truth validation | Compare derived ADSL against official ADaM ADSL from CDISC pilot | Phase 1-4 |
| Data download script | `scripts/download_data.py` — sparse checkout from PhUSE GitHub | Done (script exists) |
| Real-world edge cases | Partial dates, missing values, multi-domain joins (DM + EX + DS) | Phase 1-4 |

### Phase 6: Streamlit HITL UI

**Scope:** Web-based human-in-the-loop approval interface.

| Feature | Description | Depends On |
|---------|------------|-----------|
| Spec review page | Human reviews extracted rules, edits ambiguities, approves | Phase 3 (orchestrator HITL gates) |
| Derivation review page | Human reviews generated code, sees diff between Coder and QC | Phase 3 (verification) |
| QC results page | Human resolves QC mismatches, picks implementation, writes overrides | Phase 3 (comparator) |
| Audit trail viewer | Browse audit records, filter by variable/agent, export JSON | Phase 4 (audit trail) |
| DAG visualization | Interactive dependency graph with status coloring (green/yellow/red) | Phase 1 (DAG) |
| Workflow status | Real-time progress bar showing FSM state | Phase 3 (orchestrator) |
| DB-backed HITL gates | Workflow writes pending approvals to DB, UI polls and responds | Phase 3+4 |

### Phase 7: Docker Compose Deployment

**Scope:** Service-separated deployment testable locally.

| Feature | Description | Depends On |
|---------|------------|-----------|
| Backend container | FastAPI wrapping the orchestration engine | Phase 3 (orchestrator) |
| UI container | Streamlit multi-page app | Phase 6 |
| PostgreSQL container | Replace SQLite for long-term memory + audit | Phase 4 (memory) |
| AgentLens container | LLM proxy + guards in own container | Phase 2 (LLM gateway) |
| nginx container | Reverse proxy, load balancer | Phase 7 backend |
| Grafana/Loki container | Log aggregation + visualization | Phase 3 (loguru) |
| docker-compose.yml | Full 6-container stack, `docker compose up` | All above |
| Health checks | Container readiness + liveness probes | All containers |

### Phase 8: AgentLens Guards + Sentinel

**Scope:** Real-time circuit breaker for LLM responses.

| Feature | Description | Depends On |
|---------|------------|-----------|
| guards.yaml | Clinical-specific guard rules (patient exclusion, hardcoded values, source mutation, non-deterministic code) | Phase 7 (AgentLens container) |
| Sentinel agent | External agent reviewing escalated responses via mailbox | Phase 2 (agents) + Phase 7 |
| Guard integration test | Verify WARN/BLOCK/ESCALATE actions in the pipeline | Phase 8 guards |
| PII detection guard | Block responses containing patterns matching patient identifiers | Phase 8 guards |

### Phase 9: FastAPI HITL API

**Scope:** REST API for programmatic HITL integration (replaces Streamlit polling).

| Feature | Description | Depends On |
|---------|------------|-----------|
| `POST /workflows` | Create new workflow from spec + data | Phase 3 |
| `GET /workflows/{id}` | Get workflow status + progress | Phase 3 |
| `GET /workflows/{id}/pending` | List pending HITL approvals | Phase 6 |
| `POST /workflows/{id}/approve/{gate_id}` | Submit human decision | Phase 6 |
| `GET /workflows/{id}/audit` | Get audit trail | Phase 4 |
| `GET /workflows/{id}/dag` | Get DAG with node statuses | Phase 1 |
| WebSocket `/ws/workflows/{id}` | Real-time status updates | Phase 3 |

### Phase 10: Presentation + Design Document

**Scope:** Assignment deliverables — non-code.

| Feature | Description | Depends On |
|---------|------------|-----------|
| Design document | 2-4 page PDF consolidating ARCHITECTURE.md + ORCHESTRATION.md + REQUIREMENTS.md | All phases |
| Slide deck | 15-20 min presentation: problem framing, solution overview, demo, design decisions, limitations | All phases |
| Code map | "How to read this codebase" guide tracing a single derivation end-to-end | All code phases |
| Demo script | Step-by-step demo instructions for running the system live | Phase 7 (Docker) |

---

## Phase Dependencies

```
Phase 1 (Domain) ──────────────────────────────────────────────┐
    │                                                           │
Phase 2 (Agents) ─────────────────────────────────┐            │
    │                                              │            │
Phase 3 (Orchestration) ──────────────────┐        │            │
    │                                      │        │            │
Phase 4 (Memory + Audit + Integration)    │        │            │
    │                                      │        │            │
Phase 5 (CDISC Data) ◄────────────────────┴────────┴────────────┘
    │
Phase 6 (Streamlit UI) ◄──────────────────┐
    │                                      │
Phase 7 (Docker Compose) ◄────────────────┘
    │
Phase 8 (Guards + Sentinel)
    │
Phase 9 (FastAPI API)
    │
Phase 10 (Presentation)
```

## Priority for Homework Deadline (~Apr 15)

| Priority | Phases | Rationale |
|----------|--------|-----------|
| **P0 — Must have** | 1, 2, 3, 4 | Working engine — the core deliverable |
| **P1 — Should have** | 5, 10 | Real data validation + presentation (required deliverables) |
| **P2 — Nice to have** | 6, 7 | Streamlit UI + Docker = impressive demo |
| **P3 — Stretch** | 8, 9 | Guards + API = production depth (discuss in presentation) |

**Realistic target for Saturday (Apr 12):** P0 complete + P1 started.
**Realistic target for deadline (Apr 15):** P0 + P1 complete, P2 partially done.
