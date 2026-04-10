# Implementation Status — pharma-derive

**Last updated:** 2026-04-09
**Plan:** IMPLEMENTATION_PLAN.md

## Progress Summary

| Phase | Status | Tests | Completion |
|-------|--------|-------|------------|
| Phase 1: Domain layer | ✅ Complete | 25 | 100% |
| Phase 2: Agent definitions | ✅ Complete | 52 | 100% |
| Phase 3: Orchestration | ✅ Complete | 87 | 100% |
| Phase 4: Persistence + Audit | ✅ Complete | 118 | 100% |
| Phase 5: CDISC data | ✅ Complete | 125 | 100% |
| Phase 6: Review fixes | ✅ Complete | 148 | 100% |
| Phase 7: Streamlit UI | ⏳ Pending | — | 0% |
| Phase 8: Design doc + Presentation | ⏳ Pending | — | 0% |
| Phase 9: Docker + README | ⏳ Pending | — | 0% |

**Overall:** 6/9 phases complete (67%)

---

## Phase 5 — CDISC Pilot ADSL Spec + XPT Loader

**Implemented:** 2026-04-09
**Agent:** general-purpose
**Tooling:** ✅ All pass

### Completed
- ✅ XPT format support — pyreadstat integration with multi-domain left-join merge
- ✅ ADSL spec — 7 real CDISC derivations (AGEGR1, TRTDUR, SAFFL, ITTFL, EFFFL, DISCONFL, DURDIS)
- ✅ pyreadstat version bounds fixed (>=1.3,<2)
- ✅ 3 pre-commit checks added (file-length, llm-gateway, enum-discipline)

### Files Created
- `specs/adsl_cdiscpilot01.yaml` (52 lines)
- `tests/integration/test_cdisc.py` (62 lines)
- `tools/pre_commit_checks/check_file_length.py`
- `tools/pre_commit_checks/check_llm_gateway.py`
- `tools/pre_commit_checks/check_enum_discipline.py`

### Files Modified
- `src/domain/spec_parser.py` — XPT branch in load_source_data
- `tests/unit/test_spec_parser.py` — 3 new XPT tests
- `pyproject.toml` — pyreadstat bounds
- `.pre-commit-config.yaml` — 3 new hooks
- `QUALITY.md` — updated metrics

### Tests Added
- 3 unit tests (XPT format, DM loading, unsupported format)
- 4 integration tests (CDISC spec parse, multi-domain load, DAG layers, synthetic gen)

---

## Phase 6 — Review Fix: Deferred Items

**Implemented:** 2026-04-09
**Agent:** general-purpose
**Tooling:** ✅ All pass (148 tests, 19 import contracts)

### Completed
- ✅ 6A.1: Split orchestrator.py (243→213) — extracted WorkflowState/WorkflowResult to workflow_models.py
- ✅ 6A.2: Split spec_parser.py (175→63) — extracted source_loader.py + synthetic.py
- ✅ 6A.3: Split tools.py (197→184) — extracted CoderDeps to deps.py
- ✅ 6B.1: AuditAction + AgentName enums — replaced raw strings in orchestrator + workflow_fsm
- ✅ 6B.2: DebugContext dataclass — reduced _debug_variable from 7 to 4 params
- ✅ 6B.3: verify_derivation comment — 5 required + 2 defaults = acceptable
- ✅ 6C: Import-linter contracts — added audit-no-agents, ui-no-persistence (19 total)
- ✅ 6D.1: test_derivation_runner.py — 7 tests for _resolve_approved_code, _apply_approved, _apply_debug_fix
- ✅ 6D.2: test_logging.py — 3 tests for setup_logging
- ✅ 6D.3: FSM transition tests — 6 new tests + 1 parametrized (5 states)
- ✅ 6D.4: Persistence edge-case tests — 3 new (feedback empty, feedback limit, QC stats filter)
- ✅ 6D.5: AAA markers — added to all 9 test files

### Files Created
- `src/engine/workflow_models.py` (49 lines)
- `src/domain/source_loader.py` (57 lines)
- `src/domain/synthetic.py` (72 lines)
- `src/agents/deps.py` (21 lines)
- `src/ui/__init__.py` (placeholder for import-linter)
- `tests/unit/test_derivation_runner.py` (7 tests)
- `tests/unit/test_logging.py` (3 tests)

### Files Modified
- `src/engine/orchestrator.py` — imports updated, raw strings replaced with enums
- `src/engine/workflow_fsm.py` — AgentName/AuditAction enums
- `src/engine/derivation_runner.py` — DebugContext, imports updated
- `src/domain/models.py` — AuditAction, AgentName enums added
- `src/domain/spec_parser.py` — trimmed to parse_spec only
- `src/agents/tools.py` — CoderDeps removed
- `src/verification/comparator.py` — comment added
- `.importlinter` — 2 new contracts
- 9 test files — AAA markers added

---

## Next Phase Preview

**Phase 7: Streamlit HITL UI**
- ~7 files (app.py, theme.py, workflow page, audit page, DAG view)
- Dependencies: Phase 5 ✅, Phase 6 ✅
- Ready to start
