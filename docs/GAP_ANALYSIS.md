# Gap Analysis — Assignment Requirements vs Current State

Last updated: 2026-04-13 (post-submission code review — reclassified Memory & HITL claims that were aspirational, not implemented)

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
| 5C.1 | At least one human review step | ✅ | Single `hitl_gate` in `config/pipelines/clinical_derivation.yaml` before audit. `HITLGateStepExecutor` pauses via `asyncio.Event`, `POST /workflows/{id}/approve` releases it. Slides advertise 4 gates (spec review, QC dispute, final review, audit sign-off) — **only gate 3 is implemented** |
| 5C.2 | Reviewing or editing generated logic | ❌ | **Review-only.** `CodePanel.tsx` renders coder/QC/approved code read-only. No edit endpoint, no PATCH flow to override generated code. Gap vs. assignment "reviewing *or editing* generated logic" |
| 5C.3 | Approving outputs | ⬆️ | Single collective approval for the whole run. No per-variable approve/reject, no reject endpoint. `POST /approve` takes **no payload** (no reason, no per-variable selection) |
| 5C.4 | Resolving validation issues | ❌ | Debugger agent runs automatically on QC mismatch (good), but there is no HITL "dispute resolution" step. When debugger fails, the node stays in `DEBUG_FAILED` and the collective gate is the only escalation. Assignment asks for a dedicated human resolution path |
| 5C.5 | How feedback is captured | ❌ | Approval writes `AuditAction.HUMAN_APPROVED` to the audit trail (`step_executors.py:137`) but **`FeedbackRepository.save_feedback` is never called from the pipeline** — only tests instantiate it. No reason field, no reject payload, no per-variable feedback |
| 5C.6 | How feedback affects subsequent processing | ❌ | Current run: approval unblocks the FSM. **Cross-run: nothing persists.** The slides and design doc claim "human corrections feed back … stored and surfaced to agents in future studies" — that flow is not wired. See §5E.2 |
| **5D** | **Traceability and Auditability** | | |
| 5D.1 | Source-to-output lineage | ✅ | DAGNode carries source_columns → rule → code → result chain |
| 5D.2 | Applied transformation logic | ✅ | DAGNode.coder_code, .qc_code, .approved_code |
| 5D.3 | Agent/module responsible | ✅ | AuditRecord.agent (AgentName enum), DAGNode provenance |
| 5D.4 | Human interventions | ✅ | DAGNode.approved_by, .approved_at; FeedbackRepository |
| 5D.5 | Final output state | ✅ | WorkflowResult with qc_summary + audit_records; JSON export; DAG nodes persisted to DB |
| 5D.6 | Resolution traceability | ⬆️ | Audit records include resolution details: "debugger resolved — QC version approved" + root cause. Failed runs now emit a `workflow_failed` audit record (error, error_type, failed_step) so the UI audit tab shows *why* a run aborted |
| **5E** | **Memory and Reusability** | | |
| 5E.1 | Short-term memory (workflow state, intermediate outputs) | ✅ | `WorkflowStateRepository` wired end-to-end. Per-step checkpointing: `PipelineInterpreter.run` fires `on_step_complete`, `workflow_lifecycle.run_with_checkpoint` persists the FSM + ctx snapshot to `workflow_states`. Survives mid-run uvicorn reloads. Restart-safe rerun via `POST /workflows/{id}/rerun` |
| 5E.2 | Long-term memory (reusable logic, human feedback, validated patterns) | ❌ | **Scaffolding only — not wired.** `PatternRepository`, `FeedbackRepository`, `QCHistoryRepository` exist with ORM models and CRUD methods, but a full-codebase grep confirms they are **never instantiated outside tests**. No pipeline step queries patterns before coder runs; no post-approval hook writes patterns/feedback; QC verdicts are not written to `qc_history`. Re-running the same spec twice learns nothing |
| 5E.3 | Explain what is stored | 🔶 | docs/design.md §Memory and slides.md describe Pattern/Feedback/QCHistory/WorkflowState tables, but **database schema is not in ARCHITECTURE.md**. Only `workflow_states` is real today |
| 5E.4 | Explain how it is retrieved | 🔶 | Design doc claims "query long-term memory for matching patterns … injected as reference implementations." **No such retrieval code exists.** Coder prompts do not include historical patterns |
| 5E.5 | Explain how it improves performance | 🔶 | Aspirational — listed in slides and design doc as a benefit, but with no call site the performance improvement is zero today. Only resilience (short-term checkpointing) is real |

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
| 9.4 | Human-in-the-Loop Design | ❌ Partial | Medium | Single review gate wired. Slides overclaim 4 gates (spec, QC dispute, final, audit sign-off). No edit flow, no reject payload, no per-variable approval. See §5C |
| 9.5 | Traceability & Auditability | ✅ Implemented | High | 3-layer audit (AgentLens + loguru + AuditTrail), JSON export |
| 9.6 | Memory & Reusability | ❌ Partial | Medium | **Short-term ✅ (checkpointing, restart). Long-term ❌** — repositories exist but not wired into pipeline. Slides & design doc claim pattern reuse/feedback learning but code does not implement them. See §5E |
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
| Core Requirements (§5) | 15 | 3 | 3 | 5 | 26 |
| Input Scope (§6) | 2 | 0 | 0 | 0 | 2 |
| Technical (§7) | 4 | 2 | 0 | 0 | 6 |
| Deliverables (§8) | 3 | 1 | 0 | 0 | 4 |
| Evaluation Criteria (§9) | 4 | 1 | 0 | 2 | 7 |
| Production Design (§10) | 4 | 4 | 0 | 0 | 8 |
| Lead Expectations (§11) | 4 | 1 | 0 | 0 | 5 |
| **Total** | **36** | **12** | **3** | **7** | **58** |

**Memory and HITL are the two weak spots.** Everything technical/orchestration/traceability is solid. The code-review found that the long-term memory layer is scaffolding and the HITL story is narrower than advertised. These are the pre-submission priorities — see "Code review findings (2026-04-13)" below.

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

---

## Code review findings (2026-04-13)

Post-submission code review against the original assignment found gaps that the previous "zero gaps" summary had hidden. These are the pre-submission priorities.

### 🔴 CRITICAL — Memory story misrepresents reality (§5E)

**Problem.** `PatternRepository`, `FeedbackRepository`, `QCHistoryRepository` are defined (`src/persistence/*_repo.py`) with ORM models, CRUD methods, and unit tests, but **nothing in `src/api/`, `src/engine/`, or `src/agents/` ever instantiates them**. Only `WorkflowStateRepository` is wired.

**Evidence.**
- `grep -r PatternRepository src/` → matches only in `src/persistence/` and tests. Never in production code paths.
- `slides.md:236` claims "Before generating code: agent tools query long-term memory for matching patterns. Matches injected as reference implementations."
- `docs/design.md` §Memory claims feedback learning across runs.
- **Neither is implemented.** Re-running the same spec twice produces the same LLM calls, zero cache hits.

**Impact.** If a panelist asks "show me where a validated pattern is retrieved" or "if I approve AGEGR1 today, how does that help tomorrow's run?", we have no answer. Evaluation criterion 9.6 (Memory & Reusability) is at risk.

### 🔴 CRITICAL — HITL claims 4 gates, implements 1 (§5C)

**Problem.** `slides.md:193-198` table advertises 4 gates: Spec Review, QC Dispute, Final Review, Audit Sign-off. **Only gate 3 (Final Review) exists** in `config/pipelines/clinical_derivation.yaml`.

**Missing subcapabilities vs. assignment text.**
- "reviewing **or editing** generated logic" — no PATCH endpoint, code tabs are read-only.
- "**approving outputs**" — collective only, no per-variable approve/reject.
- "resolving validation issues" — debugger runs automatically; no dedicated human dispute flow.
- "how feedback is captured" — `/approve` takes no payload, no reject endpoint, `FeedbackRepository.save_feedback` never called.
- "how it affects subsequent processing" — next run learns nothing (ties back to §5E.2).

**Impact.** Evaluation criterion 9.4 (HITL Design) is at risk. Assignment §5C.2, 5C.4, 5C.5, 5C.6 are not fully satisfied.

### 🟠 HIGH — Ground truth validation parsed but unused

**Problem.** `specs/adsl_cdiscpilot01.yaml` declares `validation.ground_truth` pointing at the official CDISC ADaM XPT. `ValidationConfig` parses it. **Nothing in `step_builtins.py` or `step_executors.py` reads `spec.validation.ground_truth`.** The comparator only compares coder vs QC — never against ground truth. Slides/demo script imply the opposite.

**Evidence.** `grep -r ground_truth src/` shows only `src/domain/models.py` (the config class) and `src/domain/spec_parser.py` (YAML parsing). Zero runtime consumers.

**Impact.** Demo script (`slides.md:254-262`) claims "Comparator checks outputs against each other AND ground truth". Panel will ask.

### 🟠 HIGH — `guards.yaml` referenced in slides but does not exist

**Problem.** `slides.md:293` production path table lists `guards.yaml` under the Guards column. `find . -name "guards*"` returns nothing. The slide's "LLM generates, rules verify, guards enforce" framing has no artifact to back the "guards" claim in this repo (it refers to an external AgentLens proxy config).

**Fix options.** (a) Create `config/guards.yaml` stub with a few illustrative rules and reference it, (b) strike from slides + add a footnote explaining guards live in AgentLens, not the engine.

### 🟡 MEDIUM — Stale artifacts

| Artifact | State | Evidence |
|---|---|---|
| `python-statemachine` dep | Dead | Only `IMPLEMENTATION_PLAN_PHASE_3.md` references it. `src/engine/pipeline_fsm.py` is hand-rolled |
| `scripts/generate_diagrams.py` | Broken | References `src/domain/workflow_fsm.py` and `src/engine/orchestrator.py` — both deleted |
| `ARCHITECTURE.md` project structure (lines 519/537) | Stale | Still lists `workflow_fsm.py` and `orchestrator.py`; missing `src/api/*`, `src/config/settings.py`, `src/agents/factory.py`/`registry.py`, `src/engine/pipeline_*.py`, `src/engine/step_*.py` |
| `SyntheticConfig.path` field | Unused | Never read anywhere |
| `src/domain/models.py` back-compat re-exports | Unused | `ConfidenceLevel`, `CorrectImplementation`, `VerificationRecommendation`, `WorkflowStep` re-exported for callers that don't exist |
| Database schema | Undocumented | `orm_models.py` is the only source of truth; `ARCHITECTURE.md` has no §Data layer |
| `docs/design.md` format | Markdown, assignment asks for Word | Trivial `pandoc` export |

### 🟢 LOW — Explained, no action

- **`inspect_data` security model** — real df → aggregates only, synthetic CSV appended for LLM. Correct by design.
- **Debugger `tools: []`** — by design; debugger reasons on text, doesn't execute.
- **DURDIS as intentional ambiguity test** — correct; no pipeline change needed.
- **CDISC domain meaning** — DM/EX/DS/SV per SDTM IG; `source_loader` merges on USUBJID.

---

### ✅ RESOLVED (from earlier phases, retained for context)

- **ADaM Data Output (F07)** — Phase 13: CSV + Parquet export, `GET /data` preview, download endpoints, Data tab.
- **YAML-Driven Pipeline (F02/F03)** — Phase 14: `PipelineInterpreter` + `PipelineFSM` + 3 pipeline configs.
- **HITL approval endpoint** — Phase 14: `HITLGateStepExecutor` + `POST /approve` + `AuditAction.HUMAN_APPROVED`.
- **Restart-safe runs + failure visibility** — Phase 15: per-step checkpointing via `on_step_complete`, `POST /workflows/{id}/rerun` with spec_path recovery, `workflow_failed` audit record, `list_workflow_ids` fix, full cleanup on delete, `completed_at` persisted correctly.
