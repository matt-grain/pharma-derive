# Release Phases — Feature Roadmap

## All Phases Complete ✅

| Phase | Title | Key Deliverables | Status |
|-------|-------|-----------------|--------|
| **1** | Domain Layer | Models, DAG (networkx), spec parser, synthetic data, `simple_mock.yaml` | ✅ 25 tests |
| **2** | Agent Definitions | 5 PydanticAI agents, `inspect_data`/`execute_code` tools, LLM gateway | ✅ 52 tests |
| **3** | Orchestration | Workflow FSM (python-statemachine), DAG executor, QC comparator, debugger loop | ✅ 87 tests |
| **4** | Persistence + Audit | SQLAlchemy repos (SQLite), audit trail (append-only), integration tests | ✅ 118 tests |
| **—** | Architecture Review | 18 findings fixed, 3 new StrEnums, gateway enforced, 6 rules codified | ✅ 118 tests |
| **5** | CDISC Pilot Data | XPT loader (pyreadstat), ADSL spec (7 derivations), 3 new pre-commit checks | ✅ 125 tests |
| **6** | Review Fix (Deferred) | File splits (3 modules), AuditAction/AgentName enums, DebugContext, 30 new tests, AAA markers | ✅ 148 tests |
| **7** | Streamlit HITL UI | Workflow page, audit viewer, DAG visualization, AgentLens dark theme | ✅ 148 tests |
| **8** | Design Doc + Presentation | 3-page design document, 18 Marp slides with speaker notes | ✅ docs |
| **9** | Docker + README | Multi-stage Dockerfile, docker-compose, README with quick start | ✅ ops |

---

## What Was Delivered vs Original Plan

The original PHASES.md planned 10 phases with a different order. The actual implementation consolidated and reordered based on priorities and review feedback:

| Original Plan | What Actually Happened |
|--------------|----------------------|
| Phase 5: CDISC Data | ✅ Delivered as Phase 5 |
| Phase 6: Streamlit UI | ✅ Delivered as Phase 7 (after review fixes) |
| Phase 7: Docker (6 containers) | ✅ Delivered as Phase 9 (simplified to 1 container — prototype scope) |
| Phase 8: AgentLens Guards | ⏭️ Deferred — discussed in design doc as production extension |
| Phase 9: FastAPI HITL API | ⏭️ Deferred — discussed in design doc as production extension |
| Phase 10: Presentation | ✅ Delivered as Phase 8 |
| (not planned) Architecture Review | ✅ Added — 18 findings fixed, 6 rules codified, 3 pre-commit checks added |
| (not planned) Review Fix Phase | ✅ Added — file splits, missing enums, 30 new tests |

### Deferred to Production (discussed in design doc + presentation)

| Feature | Why Deferred | Where Discussed |
|---------|-------------|-----------------|
| AgentLens Guards + Sentinel | Requires live AgentLens deployment | `docs/design.md` §Trade-offs |
| FastAPI HITL API | Streamlit prototype sufficient for demo | `docs/design.md` §Production Path |
| PostgreSQL migration | SQLite adequate for prototype | `docs/design.md` §Memory Design |
| Multi-container Docker (6 services) | Single-container with external AgentLens is simpler | `docs/design.md` §Production Path |
| Alembic migrations | Not needed with SQLite file-based DB | `QUALITY.md` notes |

---

## Final Metrics

```
148 tests | 89% coverage | 19 import contracts | 18 pre-push hooks
10 custom arch checks | 0 violations | 3 deliverables (code + doc + slides)
```

## Phase Dependencies (as executed)

```
Phase 1 ─► Phase 2 ─► Phase 3 ─► Phase 4 ─► Review ─► Phase 5 ─┐
                                                                  ├─► Phase 7 ─► Phase 8 ─► Phase 9
                                                     Phase 6 ────┘
```
