# Implementation Plan — pharma-derive Engine

**Date:** 2026-04-08
**Scope:** Spec-agnostic derivation engine with `simple_mock.yaml` test scenario
**Out of scope:** CDISC data, Docker Compose, Streamlit UI, presentation
**Agent type:** `python-fastapi` (closest match — Python + Pydantic + async + pytest)
**Target:** Working end-to-end pipeline: YAML spec → DAG → agents → verify → audit trail

---

## Phase Summary

| Phase | Title | Files | Depends On | Agent |
|-------|-------|-------|-----------|-------|
| **1** | Project Setup + Domain Layer | 14 new | — | `python-fastapi` |
| **2** | Agent Definitions + LLM Gateway | 9 new | Phase 1 | `python-fastapi` |
| **3** | Orchestration Engine + Verification | 9 new | Phase 1 + 2 | `python-fastapi` |
| **4** | Memory + Audit + Integration Test | 10 new, 1 modified | Phase 1 + 2 + 3 | `python-fastapi` |

**Total:** 42 new files + 1 modified, 4 phases, ~2 implementation sessions

---

## Cross-Phase Dependencies

```
Phase 1 (Domain)
  ├── models.py         → used by ALL other phases
  ├── dag.py            → used by Phase 3 (orchestrator)
  ├── spec_parser.py    → used by Phase 3 (orchestrator)
  └── test fixtures     → used by ALL test files
         │
Phase 2 (Agents)
  ├── agent definitions → used by Phase 3 (orchestrator dispatches them)
  ├── tools.py          → shared tools for coder + QC agents
  └── llm_gateway.py    → used by Phase 3 orchestrator
         │
Phase 3 (Engine + Verification)
  ├── domain/executor.py → code execution + comparison (domain layer)
  ├── orchestrator.py    → used by Phase 4 (integration test)
  ├── comparator.py      → uses domain/executor.py (no layer violation)
  └── logging.py         → loguru configuration
         │
Phase 4 (Memory + Audit + Integration)
  ├── memory layers     → used by Phase 3 orchestrator (wired in)
  ├── audit trail       → captures full workflow provenance
  └── integration test  → end-to-end validation
```

---

## Per-Phase Plan Files

- [`IMPLEMENTATION_PLAN_PHASE_1.md`](IMPLEMENTATION_PLAN_PHASE_1.md) — Project setup, domain models, DAG, spec parser, test fixtures
- [`IMPLEMENTATION_PLAN_PHASE_2.md`](IMPLEMENTATION_PLAN_PHASE_2.md) — PydanticAI agent definitions, tools, LLM gateway
- [`IMPLEMENTATION_PLAN_PHASE_3.md`](IMPLEMENTATION_PLAN_PHASE_3.md) — Orchestrator FSM, DAG executor, QC comparator
- [`IMPLEMENTATION_PLAN_PHASE_4.md`](IMPLEMENTATION_PLAN_PHASE_4.md) — Memory (short+long term), audit trail, integration test
