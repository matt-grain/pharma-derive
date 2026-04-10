# Implementation Plan — pharma-derive

**Date:** 2026-04-09 (updated — originally 2026-04-08)
**Scope:** Full system — engine core (Phases 1-4, complete) + CDISC data, review fixes, Streamlit, docs, Docker (Phases 5-9)

## Phases 1-4 (COMPLETE)

- Phase 1: Domain layer (models, DAG, spec parser) — 25 tests
- Phase 2: Agent definitions (5 PydanticAI agents, shared tools, LLM gateway) — 27 tests
- Phase 3: Orchestration (WorkflowFSM, derivation runner, executor, comparator) — 35 tests
- Phase 4: Persistence (SQLAlchemy), audit trail, integration tests — 31 tests

**Status:** 118 tests | 85% coverage | 17 import contracts | all green
**Review:** Architecture review completed, 18/18 critical+warning fixes applied.

## Phases 5-9 (PLANNED)

| Phase | Title | Files | Agent | Dependencies |
|-------|-------|-------|-------|-------------|
| 5 | CDISC Pilot ADSL Spec + XPT Loader | ~6 | general-purpose | None |
| 6 | Review Fix — Deferred Items | ~18 | general-purpose | None (parallel-safe with 5) |
| 7 | Streamlit HITL UI | ~6 | general-purpose | Phase 5 (real data for demo) |
| 8 | Design Document + Presentation | ~3 | general-purpose | Phases 5-7 (content) |
| 9 | Docker Compose + README | ~4 | general-purpose | Phase 7 (full app) |

## Cross-Phase Dependencies

```
Phase 5 ──┐
           ├──► Phase 7 ──► Phase 8 ──► Phase 9
Phase 6 ──┘         │
                     └──► Phase 9
```

## Per-Phase Plan Files

- `IMPLEMENTATION_PLAN_PHASE_5.md` — CDISC data + XPT loader
- `IMPLEMENTATION_PLAN_PHASE_6.md` — Deferred review fixes (file splits, tests, enums)
- `IMPLEMENTATION_PLAN_PHASE_7.md` — Streamlit HITL UI
- `IMPLEMENTATION_PLAN_PHASE_8.md` — Design doc + presentation slides
- `IMPLEMENTATION_PLAN_PHASE_9.md` — Docker Compose + README
