# Implementation Plan — pharma-derive

**Date:** 2026-04-09 (updated — originally 2026-04-08)
**Scope:** Full system — COMPLETE
**Status:** ✅ ALL 9 PHASES COMPLETE

## Phases 1-4 (Engine Core)

- Phase 1: Domain layer (models, DAG, spec parser) — 25 tests
- Phase 2: Agent definitions (5 PydanticAI agents, shared tools, LLM gateway) — 27 tests
- Phase 3: Orchestration (WorkflowFSM, derivation runner, executor, comparator) — 35 tests
- Phase 4: Persistence (SQLAlchemy), audit trail, integration tests — 31 tests

## Phases 5-9 (Features + Deliverables)

| Phase | Title | Status | Tests |
|-------|-------|--------|-------|
| 5 | CDISC Pilot ADSL Spec + XPT Loader | ✅ Complete | 125 (+7) |
| 6 | Review Fix — Deferred Items | ✅ Complete | 148 (+23) |
| 7 | Streamlit HITL UI | ✅ Complete | 148 |
| 8 | Design Document + Presentation | ✅ Complete | — |
| 9 | Docker Compose + README | ✅ Complete | — |

## Phase 10 — Production Hardening Refactor ✅

15/15 findings fixed. 153 tests. See `REFACTORING.md` for details.

## Phase 11 — UI/API Split

**Date:** 2026-04-10
**Scope:** Split monolithic Streamlit app into FastAPI REST backend + Vite React SPA frontend
**Sub-phases:** 4
**Baseline:** 153 tests passing, all lint/typecheck clean

### Motivation

The Sanofi homework evaluators grade on:
- **§10.A Deployment Architecture** — service separation, containerization
- **§10.D Workflow Orchestration** — failure handling
- **§11.A Platform Thinking** — scales across studies
- **§11.E Enterprise Integration** — infrastructure constraints

A monolithic Streamlit app cannot be independently scaled, tested, or deployed. Splitting into FastAPI backend + React SPA demonstrates production architecture thinking.

### Architecture

```
┌─────────┐     ┌──────────────┐     ┌──────────────────────────┐
│  nginx   │────►│  React SPA   │     │  FastAPI Backend          │
│  :80     │     │  :3000       │────►│  :8000                    │
└─────────┘     └──────────────┘     │  ├── REST API (/api/v1/)  │
                                     │  └── MCP Server (SSE)      │
                                     └──────────┬─────────────────┘
                                                │
                                      ┌─────────┴─────────┐
                                      │    PostgreSQL      │
                                      │    :5432           │
                                      └───────────────────┘
```

### Sub-Phase Summary

| Sub-Phase | Title | New Files | Agent | Dependencies |
|-----------|-------|-----------|-------|-------------|
| 11.1 | FastAPI REST API | ~12 Python files | `python-fastapi` | None |
| 11.2 | FastMCP Thin Layer | ~3 Python files | `python-mcp-expert` | 11.1 |
| 11.3 | Vite + React SPA | ~25 TS/TSX files | `vite-react` | 11.1 |
| 11.4 | Docker Compose + nginx | ~6 config files | `general-purpose` | 11.1, 11.3 |

### Cross-Phase Dependencies

- **11.1 → 11.2:** FastMCP wraps the same service layer created in 11.1
- **11.1 → 11.3:** React frontend calls the REST API endpoints from 11.1
- **11.1 + 11.3 → 11.4:** Docker needs both backend and frontend images

### Per-Phase Plan Files

- `IMPLEMENTATION_PLAN_PHASE_11_1.md` — FastAPI REST API
- `IMPLEMENTATION_PLAN_PHASE_11_2.md` — FastMCP Layer
- `IMPLEMENTATION_PLAN_PHASE_11_3.md` — Vite + React SPA
- `IMPLEMENTATION_PLAN_PHASE_11_4.md` — Docker Compose + nginx

### Sticky Sessions

The orchestrator holds in-memory state (DataFrame + DAG) during a run. With multiple backend containers, nginx `ip_hash` ensures all requests for a workflow route to the same container. A container crash fails the workflow gracefully (FSM → `failed`). The user re-runs. Stateless backend (serialize DataFrame to blob storage between steps) is the production evolution — documented but not implemented in homework scope.

## Phase 12 — YAML Agent Config ✅

Agent configurations externalized to `config/agents/*.yaml`. Factory + registries in `src/agents/`.

## Phase 13 — ADaM Data Output (F07)

**Date:** 2026-04-11
**Scope:** Data preview API, Parquet export, frontend Data tab
**Sub-phases:** 2

| Sub-Phase | Title | Files | Agent | Dependencies |
|-----------|-------|-------|-------|-------------|
| 13.1 | Data Preview API + Parquet Export | 4 modified | `python-fastapi` | None |
| 13.2 | Frontend Data Tab | 1 new + 4 modified | `vite-react` | 13.1 |

### Cross-Phase Dependencies

- **13.1 → 13.2:** Frontend Data tab calls the `GET /workflows/{id}/data` endpoint created in 13.1

### Per-Phase Plan Files

- `IMPLEMENTATION_PLAN_PHASE_13_1.md` — Backend: schemas, data preview endpoint, Parquet export, tests
- `IMPLEMENTATION_PLAN_PHASE_13_2.md` — Frontend: types, API client, hook, DataTab component, page integration

---

## Phase 14 — YAML-Driven Orchestration Pipeline (F02/F03)

**Date:** 2026-04-11
**Scope:** Configurable pipeline via YAML, auto-generated FSM, step executors, pipeline UI diagram
**Sub-phases:** 4

### Motivation

The current orchestrator has a hardcoded step sequence in `run()`. For a platform serving multiple studies, clinical teams need to customize pipelines (skip QC for prototyping, add extra HITL gates for compliance) without touching Python code. PydanticAI handles agent abstractions but leaves orchestration/composition to the developer — this phase builds that composition layer.

### Sub-Phase Summary

| Sub-Phase | Title | New Files | Modified | Agent | Dependencies |
|-----------|-------|-----------|----------|-------|-------------|
| 14.1 | Pipeline models + step executors | 4 new + 2 test | 1 modified | `python-fastapi` | None |
| 14.2 | Pipeline interpreter + FSM auto-gen + default YAML | 3 new + 1 test + 1 doc | 1 modified | `python-fastapi` | 14.1 |
| 14.3 | API endpoint + frontend PipelineView | 2 new + 5 modified | — | `python-fastapi` + `vite-react` | 14.2 |
| 14.4 | Scenario pipelines (express, enterprise) + tests | 2 YAML + 2 test | — | `python-fastapi` | 14.2 |

### Cross-Phase Dependencies

- **14.1 → 14.2:** Interpreter uses models + executors from 14.1
- **14.2 → 14.3:** API endpoint serves the pipeline YAML created in 14.2
- **14.2 → 14.4:** Scenario YAMLs use the same schema; tests use the interpreter from 14.2
- **14.3 and 14.4 are independent** — can run in parallel

### Per-Phase Plan Files

- `IMPLEMENTATION_PLAN_PHASE_14_1.md` — Pipeline domain models + step executors + tests
- `IMPLEMENTATION_PLAN_PHASE_14_2.md` — Pipeline interpreter + topological sort + default YAML + COMPOSITION_LAYER.md
- `IMPLEMENTATION_PLAN_PHASE_14_3.md` — API endpoint + frontend ReactFlow pipeline diagram
- `IMPLEMENTATION_PLAN_PHASE_14_4.md` — Express + enterprise YAML configs + scenario tests + integration tests

---

## Final Metrics

- **153 tests** | **89% coverage** | **19 import contracts** | **18 pre-push hooks**
- **10 custom architectural checks** (all green)
- **3 deliverables**: design doc, presentation slides, working prototype
