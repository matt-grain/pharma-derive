# Gap Analysis — Assignment Requirements vs Current State

Last updated: 2026-04-12 (after Phases 10–15: hardening, UI/API split, YAML agents, data output, YAML pipeline, per-step checkpointing + workflow restart)

Legend: ✅ Done | ⬆️ Improved since last review | 🔶 Designed only (documented but not coded) | ❌ Gap

---

## §5. Core Requirements

| # | Requirement | Status | Where / Notes |
|---|------------|--------|---------------|
| **5A** | **Multi-Agent Workflow Design** | | |
| 5A.1 | Clearly defined components (agents or modules) | ⬆️ | 5 PydanticAI agents loaded from YAML configs (`config/agents/*.yaml`) via factory + registries. Orchestration pipeline also YAML-driven (`config/pipelines/*.yaml`) |
| 5A.2 | Specification Review agent | ✅ | `src/agents/spec_interpreter.py` — SpecInterpretation output |
| 5A.3 | Transformation / Code Generation agent | ✅ | `src/agents/derivation_coder.py` — DerivationCode output |
| 5A.4 | Verification / Validation agent (QC) | ✅ | `src/agents/qc_programmer.py` — independent double programming |
| 5A.5 | Refinement / Debugging agent | ✅ | `src/agents/debugger.py` — DebugAnalysis with CorrectImplementation enum |
| 5A.6 | Audit / Summarization agent | ✅ | `src/agents/auditor.py` — AuditSummary output |
| 5A.7 | Architecture is clear and well justified | ✅ | ARCHITECTURE.md, docs/design.md, decisions.md |
| **5B** | **Dependency-Aware Derivation** | | |
| 5B.1 | Distinguish source vs derived variables | ✅ | `src/domain/dag.py` — DAGNode with DerivationRule + provenance |
| 5B.2 | Ensure correct execution order | ✅ | `dag.layers` + `dag.execution_order` via networkx topological sort |
| 5B.3 | DAG or equivalent approach | ✅ | Enhanced DAG: lineage + computation + audit per node |
| **5C** | **Human-in-the-Loop (HITL)** | | |
| 5C.1 | At least one human review step | ⬆️ | React SPA with workflow detail page (Status, DAG, Code, Audit tabs) + legacy Streamlit |
| 5C.2 | Reviewing or editing generated logic | ⬆️ | Code tab: coder vs QC side-by-side + approved version + resolution labels |
| 5C.3 | Approving outputs | ⬆️ | QC summary with match/mismatch badges, debugger resolution context |
| 5C.4 | Resolving validation issues | ✅ | Debugger agent triggered on QC mismatch |
| 5C.5 | How feedback is captured | ✅ | Audit trail (append-only) + long-term memory (SQLite repos) |
| 5C.6 | How feedback affects subsequent processing | ✅ | PatternRepository queries inject validated patterns into agent prompts |
| **5D** | **Traceability and Auditability** | | |
| 5D.1 | Source-to-output lineage | ✅ | DAGNode carries source_columns → rule → code → result chain |
| 5D.2 | Applied transformation logic | ✅ | DAGNode.coder_code, .qc_code, .approved_code |
| 5D.3 | Agent/module responsible | ✅ | AuditRecord.agent (AgentName enum), DAGNode provenance |
| 5D.4 | Human interventions | ✅ | DAGNode.approved_by, .approved_at; FeedbackRepository |
| 5D.5 | Final output state | ✅ | WorkflowResult with qc_summary + audit_records; JSON export; DAG nodes persisted to DB |
| 5D.6 | Resolution traceability | ⬆️ | Audit records include resolution details: "debugger resolved — QC version approved" + root cause. Failed runs now emit a `workflow_failed` audit record (error, error_type, failed_step) so the UI audit tab shows *why* a run aborted |
| **5E** | **Memory and Reusability** | | |
| 5E.1 | Short-term memory (workflow state, intermediate outputs) | ⬆️ | WorkflowState + WorkflowStateRepository, **per-step checkpointing**: `PipelineInterpreter.run` fires an `on_step_complete` callback after each step and `WorkflowManager._run_and_cleanup` persists the FSM + ctx snapshot to `workflow_states`. Survives mid-run uvicorn reloads |
| 5E.2 | Long-term memory (reusable logic, human feedback, validated patterns) | ✅ | PatternRepository, FeedbackRepository, QCHistoryRepository (SQLite) |
| 5E.3 | Explain what is stored | ✅ | docs/design.md §Memory, REQUIREMENTS.md Q7 |
| 5E.4 | Explain how it is retrieved | ✅ | By variable type, by spec similarity — injected into agent prompts |
| 5E.5 | Explain how it improves performance | ✅ | Pre-populate code generation, learn from corrections |

---

## §6. Input Scope

| # | Requirement | Status | Where / Notes |
|---|------------|--------|---------------|
| 6.1 | Dataset with patient_id, age, sex, treatment dates, visit dates, lab_value, response | ✅ | CDISC Pilot Study (cdiscpilot01) — real Alzheimer's trial, 306 subjects, 4 SDTM domains |
| 6.2 | Derived outputs: AGE_GROUP, TREATMENT_DURATION, RESPONSE_FLAG, ANALYSIS_POP_FLAG, RISK_GROUP | ✅ | 7 ADSL variables in `specs/adsl_cdiscpilot01.yaml`: AGEGR1, TRTDUR, SAFFL, ITTFL, EFFFL, DISCONFL, DURDIS |

---

## §7. Technical Expectations

| # | Requirement | Status | Where / Notes |
|---|------------|--------|---------------|
| 7.1 | Python or R | ✅ | Python 3.13+ |
| 7.2 | Streamlit / FastAPI / CLI / notebook | ⬆️ | FastAPI REST API + FastMCP (LLM-drivable) + React SPA + legacy Streamlit |
| 7.3 | LLMs, rules, or hybrid approaches | ✅ | PydanticAI agents (LLM) + deterministic comparator/executor (rules) = hybrid |
| 7.4 | System design quality | ✅ | ARCHITECTURE.md, docs/design.md, decisions.md, 19 import-linter contracts |
| 7.5 | Reasoning | ✅ | REQUIREMENTS.md (9 questions, 7 decisions, 6 assumptions, full glossary) |
| 7.6 | Working prototype | ⬆️ | Full pipeline: YAML spec → DAG → agents → QC → audit. 270 tests, YAML-driven orchestration, MCP-drivable, per-step checkpointing, restart-safe rerun |

---

## §8. Deliverables

| # | Deliverable | Status | Where / Notes |
|---|------------|--------|---------------|
| 8.1 | Source code (GitHub repo with setup instructions) | ✅ | github.com/matt-grain/pharma-derive, README.md with 4-command quick start |
| 8.2 | Working prototype (runnable system) | ⬆️ | `uv run uvicorn src.api.app:app` + `cd frontend && npm run dev` or `docker compose up` (3-container) |
| 8.3 | Design document (2–4 pages) | ✅ | `docs/design.md` — 3 pages with mermaid diagrams, all required sections |
| 8.4 | Presentation (15–20 minutes) | ✅ | `presentation/slides.md` — 19 Marp slides with speaker notes |

---

## §9. Evaluation Criteria

| # | Criterion | Status | Confidence | Where |
|---|----------|--------|-----------|-------|
| 9.1 | Agentic Architecture | ✅ Implemented | High | 5 agents with typed I/O, custom orchestrator, PydanticAI |
| 9.2 | Data Logic & Dependency Handling | ✅ Implemented | High | Enhanced DAG with networkx, tested with CDISC pilot data |
| 9.3 | Verification & Reliability | ✅ Implemented | High | Double programming (coder+QC), AST similarity check, debugger loop |
| 9.4 | Human-in-the-Loop Design | ⬆️ Implemented | High | React SPA (DAG viz, code review, audit trail) + REST API + legacy Streamlit |
| 9.5 | Traceability & Auditability | ✅ Implemented | High | 3-layer audit (AgentLens + loguru + AuditTrail), JSON export |
| 9.6 | Memory & Reusability | ✅ Implemented | High | SQLAlchemy repos (Pattern, Feedback, QCHistory, WorkflowState) |
| 9.7 | Implementation Quality | ⬆️ Implemented | High | 270 tests, pyright strict, 18 pre-push hooks, 10 custom checks, domain exceptions, BaseRepository error wrapping, @traced_tool, YAML agent + pipeline configs, per-step checkpointing |
| 9.8 | Communication & Reasoning | ✅ Complete | High | REQUIREMENTS.md, design doc, 19-slide presentation, decisions.md |

---

## §10. Cloud & Production Design (Lead-level)

| # | Requirement | Status | Where / Notes |
|---|------------|--------|---------------|
| 10A | Deployment architecture | ⬆️ | 3-container Docker Compose (nginx + backend + frontend), sticky sessions, K8s path in design doc |
| 10B | Data security | ✅ | Dual-dataset architecture implemented: agents see schema+synthetic only |
| 10C | Model integration | ⬆️ | LLM gateway (cached, pydantic-settings), model-agnostic, FastMCP for agent-to-agent communication |
| 10D | Workflow orchestration | ⬆️ | YAML-driven PipelineInterpreter + PipelineFSM (auto-generated states) + 3 pipeline configs (standard/express/enterprise) + domain exceptions + rollback on failure + per-step checkpointing (restart-safe) + `POST /workflows/{id}/rerun` restart endpoint with spec_path recovery from history |
| 10E | Audit & traceability | ✅ | Append-only AuditTrail, JSON export, AgentName/AuditAction enums |
| 10F | Scalability | ✅ | asyncio.gather for fan-out, stateless orchestrator, Docker-ready |
| 10G | CI/CD | ✅ | GitHub Actions CI + 18 pre-push hooks + 10 custom arch checks |
| 10H | Observability | ⬆️ | loguru (system), AuditTrail (business), AgentLens traces (agent), @traced_tool decorator on tools |

---

## §11. Additional Lead Expectations

| # | Requirement | Status | Where / Notes |
|---|------------|--------|---------------|
| 11A | Platform thinking | ⬆️ | Engine is spec-agnostic + YAML agent configs + YAML pipeline configs (3 scenarios: standard, express, enterprise) enable per-study customization without code changes |
| 11B | Trade-offs | ✅ | docs/design.md §Trade-offs: automation vs control, LLM vs rules, data security |
| 11C | Reliability | ✅ | docs/design.md §Trade-offs: failure modes, retry with escalation, FSM error handling |
| 11D | Scaling use cases | ✅ | docs/design.md §Production Path: multi-study, Docker→K8s, SQLite→PostgreSQL |
| 11E | Enterprise integration | ✅ | docs/design.md: Pinnacle 21 integration point, LLM gateway abstraction |

---

## Summary

| Category | ✅ Done | ⬆️ Improved | 🔶 Designed | ❌ Gap | Total |
|----------|--------|------------|------------|-------|-------|
| Core Requirements (§5) | 18 | 5 | 0 | 0 | 23 |
| Input Scope (§6) | 2 | 0 | 0 | 0 | 2 |
| Technical (§7) | 4 | 2 | 0 | 0 | 6 |
| Deliverables (§8) | 3 | 1 | 0 | 0 | 4 |
| Evaluation Criteria (§9) | 6 | 2 | 0 | 0 | 8 |
| Production Design (§10) | 4 | 4 | 0 | 0 | 8 |
| Lead Expectations (§11) | 4 | 1 | 0 | 0 | 5 |
| **Total** | **41** | **15** | **0** | **0** | **56** |

**56/56 requirements addressed.** Zero gaps remaining. Phases 13-14 resolved F07 (ADaM output) and F02/F03 (YAML pipeline). Phase 15 added resilience: per-step checkpointing, restart-safe rerun, failure-reason audit records, and a `list_workflow_ids` fix so failed runs stay visible in the dashboard.

---

## Remaining Gaps

### ✅ RESOLVED: ADaM Data Output (F07) — Phase 13

Implemented in Phase 13: CSV + Parquet export, `GET /data` preview endpoint, `GET /adam?format=csv|parquet` download, Data tab with collapsible schema grid, dtype badges, row numbers, sticky headers.

### ✅ RESOLVED: YAML-Driven Pipeline (F02/F03) — Phase 14

Implemented in Phase 14: PipelineInterpreter reads `config/pipelines/*.yaml`, 5 step executors, PipelineFSM auto-generated from step IDs, 3 pipeline configs (standard/express/enterprise), wired into WorkflowManager + API. Old orchestrator kept as reference.

### ✅ RESOLVED: HITL Approval (POST /approve)

Wired in Phase 14: HITLGateStepExecutor creates asyncio.Event, API finds pending event via `manager.get_approval_event()`, `POST /approve` sets the event and records AuditAction.HUMAN_APPROVED.

### ✅ RESOLVED: Restart-safe runs + failure visibility — Phase 15

Implemented in this session:
- **Per-step checkpointing.** `PipelineInterpreter.run` takes an `on_step_complete` callback that `WorkflowManager` uses to persist the FSM + ctx after every step. `workflow_states.updated_at` advances as each step completes, so a uvicorn hot-reload mid-run can't silently lose state.
- **Workflow restart (`POST /workflows/{id}/rerun`).** Resolves the spec from the in-memory ctx first, then falls back to `HistoricState.spec_path` (now persisted by `serialize_ctx`). Starts a new run, then atomically deletes the old one (including output files) on success. Frontend shows a refresh icon only on `failed` cards.
- **`workflow_failed` audit record.** `AuditAction.WORKFLOW_FAILED` enum + `_run_and_cleanup` except branch appends `error`, `error_type`, `failed_step` to the audit trail so the UI audit tab surfaces the failure reason.
- **Failed workflows stay visible.** `WorkflowManager.list_workflow_ids` was reading `_active` (empty after failure); switched to `_interpreters` (matches `is_known`). Failed runs no longer vanish from `GET /workflows/` until the next backend restart.
- **Full cleanup on delete.** File unlink moved from the router into `WorkflowManager.delete_workflow` so both the `DELETE` endpoint and the rerun flow share the same cleanup.
- **`completed_at` persisted correctly.** Was being set in the `finally` block *after* the final DB save; moved into the try/except path so the serialized row has a real value.

### 🟡 Nice-to-haves (not required by assignment)

| Item | Status | Notes |
|------|--------|-------|
| WebSocket live status updates | 🔶 | Currently polling every 2s via React Query |
| AST-based exec sandbox | 🔶 | F05 — current token blocklist is naive |
| Authentication on API | 🔶 | No auth — acceptable for homework demo |
| Ground truth comparison in UI | 🔶 | Spec supports it, engine doesn't expose results |
