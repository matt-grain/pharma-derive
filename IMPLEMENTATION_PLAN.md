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

## Phase 16 — Close Code-Review Gaps

**Date:** 2026-04-13
**Branch:** `feat/phase-16-gap-close` (from `feat/yaml-pipeline`)
**Source of gaps:** `docs/GAP_ANALYSIS.md` → "Code review findings (2026-04-13)"
**Critical assignment items:** Memory (§5E) + HITL (§5C) — all other sub-phases are support cleanup.

### Sub-phase summary

| Phase | Title | Agent | New/Mod/Del | Depends on | Fixes |
|-------|-------|-------|-------------|------------|-------|
| 16.1 | Long-term memory wiring | `python-fastapi` | 5 / 9 / 0 | — | §5E.2, 5E.4, 5E.5, 9.6, 5C.6 |
| 16.4 | Ground truth comparison at runtime | `python-fastapi` | 2 / 4 / 0 | 16.1 (shared `pipeline_context.py`) | Slide demo claim §262 |
| 16.2a | HITL backend plumbing | `python-fastapi` | 0 / 5 / 0 | 16.1 | Sets up exceptions, ctx fields, rejection flag |
| 16.2b | HITL backend API surface | `python-fastapi` | 2 / 3 / 0 | 16.2a, 16.4 (shared `workflows.py`, `schemas.py`) | §5C.3, 5C.5, 9.4 |
| 16.3.0 | Frontend test infra setup | `vite-react` | 2 / 2 / 0 | — | Adds vitest + RTL (missing from `frontend/`) |
| 16.3a | HITL frontend plumbing | `vite-react` | 1 / 3 / 0 | 16.2b, 16.3.0 | Types, API client, hooks, textarea primitive |
| 16.3b | HITL frontend dialogs + wiring | `vite-react` | 7 / 3 / 0 | 16.3a | §5C.2, 5C.3, 9.4 — 4 dialogs, 3 mods, tests |
| 16.5 | Cleanup + docs | `python-fastapi` + orchestrator | 1 / 5 / 1 | — | Stale artifacts, guards.yaml, DB schema |
| 16.6 | design.md → docx | orchestrator (pandoc) | 1 / 0 / 0 | — | Word deliverable format |

### Execution order

**Sequenced, not parallel** on the critical path. Phases 16.1/16.2/16.4 all modify overlapping files (`pipeline_context.py`, `step_builtins.py`, `clinical_derivation.yaml`, `workflows.py` routes, `schemas.py`) — parallel execution would cause merge conflicts. Only 16.5 (backend cleanup) and 16.3.0 (frontend test infra) are truly independent and can run in side branches.

```
START
│
├─▶ 16.5 (Backend cleanup)         ── parallel side branch A
│
├─▶ 16.3.0 (Frontend test infra)    ── parallel side branch B
│
└─▶ 16.1 (Memory wiring)
        │
     16.1 done ──▶ 16.4 (Ground truth)
                        │
                 16.4 done ──▶ 16.2a (HITL plumbing)
                                     │
                              16.2a done ──▶ 16.2b (HITL API surface)
                                                   │
                                      16.2b done ──▶ 16.3a (Frontend plumbing — needs 16.3.0 too)
                                                          │
                                                   16.3a done ──▶ 16.3b (Frontend dialogs + wiring)
                                                                        │
                                                                        ▼
                                                                   16.6 (pandoc docx)
```

**Critical path:** 16.1 → 16.4 → 16.2a → 16.2b → 16.3a → 16.3b → 16.6. **16.5 and 16.3.0 run independently.**

**16.3a requires BOTH 16.2b (API surface) AND 16.3.0 (test infra) to be complete before it can start.**

### Cross-phase dependencies

- **16.1 → 16.4:** 16.1 adds `session: AsyncSession | None` field to `PipelineContext`. 16.4 adds `ground_truth_report: GroundTruthReport | None` field to the same file. Sequenced (not parallel) to avoid merge conflict on `pipeline_context.py` and `step_builtins.py` (both add a builtin to `BUILTIN_REGISTRY`) and `clinical_derivation.yaml` (both add a step).
- **16.4 → 16.2:** 16.4 adds a route to `workflows.py` and schemas to `schemas.py`. 16.2 adds 3 routes and 4 schemas to the same files. Sequenced to avoid merge conflict.
- **16.1 → 16.2 (semantic):** 16.1 adds `AsyncSession` plumbing + exposes `WorkflowManager.get_session(wf_id)`. 16.2 reuses that session in `/approve` and `/reject` route handlers to write to `FeedbackRepository` without opening a second session.
- **16.2 → 16.3:** 16.2 produces the API surface (`POST /approve` with body, `POST /reject`, `POST /variables/{var}/override`). 16.3 consumes via typed client wrappers in `frontend/src/lib/api.ts`.
- **16.5 orchestrator tasks → all phases:** ARCHITECTURE.md regeneration and `decisions.md` ADR writes happen *after* 16.1–16.4 merge, so docs reflect final state. Sonnet cleanup subtasks (5.1–5.4) are independent and run in parallel on their own branch.
- **Architectural exceptions:** Phases 16.1 and 16.2 both require extending `.importlinter` `ignore_imports` lists to allow `agents→persistence`, `engine→persistence`, and `api→persistence` for specific new edges. These are deliberate exceptions, not violations — they follow the existing exception pattern for `workflow_manager → workflow_state_repo`.

### Per-phase plan files

- `IMPLEMENTATION_PLAN_PHASE_16_1.md` — Long-term memory wiring (tools, builtins, DB session plumbing, `.importlinter` exceptions)
- `IMPLEMENTATION_PLAN_PHASE_16_4.md` — Ground truth comparison builtin + endpoint
- `IMPLEMENTATION_PLAN_PHASE_16_2_A.md` — HITL backend plumbing: exceptions, ctx fields, rejection flag, `.importlinter` exceptions
- `IMPLEMENTATION_PLAN_PHASE_16_2_B.md` — HITL backend API surface: schemas, override_service, workflow_manager methods, routes
- `IMPLEMENTATION_PLAN_PHASE_16_3_0.md` — Frontend test infra: vitest + RTL setup (independent)
- `IMPLEMENTATION_PLAN_PHASE_16_3_A.md` — Frontend plumbing: types, lib/api, hooks, ui/textarea primitive
- `IMPLEMENTATION_PLAN_PHASE_16_3_B.md` — Frontend dialogs + wiring: RejectDialog, ApprovalDialog, VariableApprovalList, CodeEditorDialog + mods + tests
- `IMPLEMENTATION_PLAN_PHASE_16_5.md` — Cleanup + docs + Phase 16.6 pandoc command

### Mapping back to the code review

| Review point | Fixed in |
|---|---|
| Long-term memory not wired | **16.1** |
| HITL 4 gates vs 1 (depth, not count) | **16.2** + **16.3** + slide edit |
| No reject / no feedback payload | **16.2** + **16.3** |
| Ground truth parsed but unused | **16.4** |
| `python-statemachine` dead dep | **16.5** |
| `scripts/generate_diagrams.py` broken | **16.5** |
| `ARCHITECTURE.md` stale project structure | **16.5** |
| Unused `SyntheticConfig.path` + back-compat re-exports | **16.5** |
| `config/guards.yaml` missing | **16.5** |
| DB schema undocumented | **16.5** |
| `design.md` not in Word format | **16.6** |

---

## Final Metrics

- **153 tests** | **89% coverage** | **19 import contracts** | **18 pre-push hooks**
- **10 custom architectural checks** (all green)
- **3 deliverables**: design doc, presentation slides, working prototype
