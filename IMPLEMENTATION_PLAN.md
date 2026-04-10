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

## Phase 10 — Production Hardening Refactor

**Date:** 2026-04-10
**Features:** 9 refactoring items + quality quick wins
**Sub-phases:** 3
**Agent:** `python-fastapi` (all sub-phases)
**Baseline:** 148 tests passing, all lint/typecheck clean

### Motivation

The Sanofi homework evaluators explicitly grade on:
- **§9.7 Implementation Quality** — code structure, modularity, readability
- **§11.C Reliability** — failure modes, error propagation
- **§10.D Workflow Orchestration** — failure handling

Current codebase has PoC shortcuts (asserts as guards, zero DB error handling, fragile manual DAG updates, misplaced modules) that directly cost points.

### Sub-Phase Summary

| Sub-Phase | Title | Files Changed | Dependencies |
|-----------|-------|--------------|-------------|
| 10.1 | Foundation — New Types + Module Restructure | ~25 new/moved | None |
| 10.2 | Wiring — Use New Structures | ~15 modified | 10.1 |
| 10.3 | Polish — Quality Quick Wins | ~12 modified | 10.2 |

### Cross-Phase Dependencies

- **10.1 → 10.2:** Phase 10.1 creates domain exceptions, `DerivationRunResult`, `BaseRepository`, `src/config/`, `src/agents/tools/` package. Phase 10.2 wires these into existing modules.
- **10.2 → 10.3:** Phase 10.2 stabilizes all imports and behavior. Phase 10.3 adds docstrings, type hints, and config cleanup on the stabilized code.

### Per-Phase Plan Files

- `IMPLEMENTATION_PLAN_PHASE_10_1.md` — Foundation
- `IMPLEMENTATION_PLAN_PHASE_10_2.md` — Wiring
- `IMPLEMENTATION_PLAN_PHASE_10_3.md` — Polish

## Final Metrics

- **148 tests** | **89% coverage** | **19 import contracts** | **18 pre-push hooks**
- **10 custom architectural checks** (all green)
- **3 deliverables**: design doc, presentation slides, working prototype
