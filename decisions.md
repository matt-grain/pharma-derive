# Architecture Decision Records

## 2026-04-08 — Use CDISC Pilot Study Instead of Synthetic Data

**Status:** accepted
**Context:** The assignment allows us to define our own dataset. We could generate mock data or use a real public clinical trial dataset.
**Decision:** Use the CDISC Pilot Study (cdiscpilot01) from the PhUSE GitHub repository — an Alzheimer's disease trial with full SDTM and ADaM data.
**Alternatives considered:** Generating synthetic mock data with Faker or similar tools.
**Consequences:** Real data provides ground truth for verification (our derived ADaM can be compared against the official ADaM). Signals domain fluency to the panel. Adds complexity from real-world edge cases (partial dates, missing values).

## 2026-04-08 — Enhanced DAG (Lineage + Computation + Audit)

**Status:** accepted
**Context:** The assignment requires a DAG or equivalent for dependency-aware derivation. A standard DAG only carries execution order ("compute A before B").
**Decision:** Enrich each DAG node with: derivation rule, generated code, agent provenance, QC status, and human approval metadata.
**Alternatives considered:** Standard dependency-only DAG with separate audit log; dbt-style lineage graph.
**Consequences:** The DAG becomes the single source of truth for execution, lineage, AND audit. Slightly more complex node model but eliminates the need for separate lineage tracking. Aligns with 21 CFR Part 11 traceability requirements.

## 2026-04-08 — PydanticAI for Agents, Custom Orchestration for Workflow

**Status:** accepted (validated by prototype)
**Context:** Initially considered CrewAI but evaluation of v1.10+ revealed: `async_execution=True` has bugs (PR #2466), `human_input=True` is CLI-only, Hierarchical process is unpredictable, Consensual not implemented. Evaluated PydanticAI as alternative.

**Decision:** Use PydanticAI for agent definition, structured output, and tool binding. Build a custom orchestration layer (Python async + workflow FSM) for workflow control, parallelism, HITL gates, and error handling.

**Prototype validation (2026-04-08):** 5/5 tests passed:
1. Single agent + structured Pydantic output via AgentLens mailbox ✓
2. Two parallel agents via `asyncio.gather` (true parallelism confirmed) ✓
3. Multi-turn tool use (inspect → execute → final_result) ✓
4. Typed dependency injection via `RunContext[DepsType]` ✓
5. Full Spec → Coder+QC parallel → Compare orchestration ✓

**Alternatives considered:**
- CrewAI (rejected: async bugs, CLI-only HITL, stringly-typed, no native Pydantic output)
- LangGraph (rejected: heavy LangChain dependency, graph-first not agent-first)
- Pure custom agents / thin SDK wrapper (rejected: assignment requires "multi-step agentic workflow, not a simple LLM wrapper")
- AutoGen (rejected: adds second framework complexity)

**Consequences:** PydanticAI gives us type-safe agents, true async, structured validated output, dependency injection, and native MCP support. Custom orchestration gives full control over parallelism, HITL, and error handling. Story to panel: "We chose PydanticAI for type-safe agent abstractions and built domain-specific orchestration for clinical workflows."

## 2026-04-08 — AgentLens as Observer, Evaluator, AND Circuit Breaker

**Status:** accepted
**Context:** The assignment asks for observability (logging, monitoring, metrics) and audit/traceability (audit logs, lineage storage, versioning). Additionally, Shanshan Zhu (hiring manager) specifically suggested using AgentLens to "observe AND act."
**Decision:** AgentLens serves three roles: (1) trajectory tracing (observer), (2) deterministic evaluation of every LLM response, (3) real-time circuit breaker via guards that can warn, block, or escalate responses before the agent framework sees them. A Sentinel agent handles escalations via the mailbox.
**Alternatives considered:** Custom logging + LangSmith (no circuit breaker capability); separate evaluation pipeline (post-hoc only).
**Consequences:** Single infrastructure component covers observability + evaluation + safety. Guards configuration is per-study, enabling different compliance levels. The Sentinel agent is an extension point for CDISC-aware review in production.

## 2026-04-08 — Production Engineering Discipline on Homework

**Status:** accepted
**Context:** The assignment says "prototype" but evaluates "implementation quality" and the Lead role expects "production readiness" thinking.
**Decision:** Apply full engineering discipline: ruff, pyright strict, pytest >80% coverage on core logic, GitHub Actions CI, ARCHITECTURE.md, decisions.md, typed interfaces throughout.
**Alternatives considered:** Jupyter notebook with inline documentation (typical for academic/DS submissions).
**Consequences:** Differentiates from PhD-heavy candidates who submit notebooks. Slightly more setup time but demonstrates the system could be deployed and maintained by a team. Engineering practices are our default workflow — minimal additional effort.

## 2026-04-09 — python-statemachine for Workflow FSM

**Status:** superseded by Phase 14 YAML pipeline engine (2026-04-11) + Phase 16.5 cleanup (2026-04-13)
**Context:** The orchestration workflow has 10 states and ~18 transitions, with audit requirements (every transition must be logged for 21 CFR Part 11 traceability). Initial plan used a hand-rolled dict + transition function (~15 lines).
**Decision:** Use `python-statemachine` v3.0 for the workflow FSM. Define states/transitions declaratively with `on_enter_state` callbacks for automatic logging and audit trail generation.
**Alternatives considered:** Hand-rolled `VALID_TRANSITIONS` dict with `transition()` function (simpler, no dependency). Rejected because audit logging on every transition would require manual `logger.info()` + `audit_records.append()` after every call — error-prone and repetitive.
**Consequences:** Small dependency (pure Python, no transitive deps). Transition callbacks handle audit logging declaratively. `.graph()` export available for panel presentation diagrams. FSM is independently testable. Trade-off: slightly more ceremony in class definition vs. a 15-line function.

**Supersession note (2026-04-13):** Phase 14 replaced the hardcoded FSM with `PipelineFSM` — a lightweight state tracker whose states are **auto-derived from the step IDs of whichever YAML pipeline is running**. `express.yaml` (4 steps), `clinical_derivation.yaml` (8 steps), and `enterprise.yaml` (9 steps) now each get their own FSM topology without code duplication. The `python-statemachine` dependency was removed in Phase 16.5 (Task 5.1) once every caller had migrated to `PipelineFSM`. Audit logging moved into the `PipelineInterpreter` step dispatch loop (emits `STEP_STARTED`/`STEP_COMPLETED`/`HUMAN_APPROVED`/`HUMAN_REJECTED`/`HUMAN_OVERRIDE`/`WORKFLOW_FAILED` via `AuditTrail.record`). The new design scales to arbitrary pipelines — the original 10-state hardcoded FSM would have needed edits for every new workflow variant.

## 2026-04-09 — SQLAlchemy for Persistence (not raw sqlite3)

**Status:** accepted
**Context:** The engine needs persistent storage for validated patterns, QC history, workflow state, and feedback. Initial plan used raw `sqlite3` with a comment "swap to PostgreSQL later". The panel evaluates "production readiness" explicitly.
**Decision:** Use SQLAlchemy 2.0 async (`AsyncSession`, `Mapped[]`, `mapped_column()`) with `aiosqlite` driver for local dev and `asyncpg` for PostgreSQL. Repository pattern: orchestrator depends on repository interfaces, never on sessions or ORM directly.
**Alternatives considered:** (1) Raw `sqlite3` (simpler, zero deps) — rejected because "swap later" is tech debt theater; the panel will see a SQLite-locked prototype. (2) Raw `asyncpg` for PostgreSQL only — rejected because local dev without Docker requires SQLite.
**Consequences:** Zero-code-change deployment path: `sqlite+aiosqlite:///cdde.db` (local) → `postgresql+asyncpg://...` (Docker/prod) via a single `DATABASE_URL` env var. Repository layer adds ~100 lines of infra code but enforces clean separation: ORM models ≠ domain models, repositories return Pydantic schemas. Tests use `sqlite+aiosqlite:///:memory:` — same code path, no mocking.

## 2026-04-10 — Production Hardening Refactor (Phase 10)

**Status:** accepted
**Context:** Code review identified PoC shortcuts that cost points on §9.7 Implementation Quality and §11.C Reliability: assert-as-guards, zero DB error handling, fragile manual DAG updates, misplaced modules, no tool tracing.
**Decision:** Refactor in 3 sub-phases: (1) new types + module restructure, (2) wire behavioral changes, (3) quality polish. No feature changes — pure structural improvement.
**Alternatives considered:** Fixing only critical items (asserts + DB errors) and leaving module structure. Rejected because evaluators also grade on "code structure, modularity, readability" — the module layout issues are visible to a reviewer scanning the tree.
**Consequences:** ~25 files touched. Import paths change (mitigated by __init__.py re-exports). Test count increases. Module structure now matches ARCHITECTURE.md claims.

## 2026-04-09 — Orchestrator as Application Service (No Separate Service Layer)

**Status:** accepted
**Context:** Traditional layered architecture (Fowler, PoEAA) places a Service Layer between controllers and repositories. Should we insert a service layer between the orchestrator and the persistence repositories?
**Decision:** No separate service layer. The orchestrator IS the application service — it coordinates domain operations (DAG, agents, verification) and uses repositories for persistence via constructor DI. Adding `PatternService`, `FeedbackService` etc. would create pure pass-through classes with no business logic.
**Alternatives considered:** (1) Dedicated service classes per domain concept (PatternService, QCService) — rejected because the business rules ("store pattern after QC pass", "query patterns before derivation") are workflow decisions that live in the orchestrator, not in pattern-management services. A service layer here would be an anemic pass-through (Fowler, "Anemic Domain Model", 2003). (2) CQRS with separate read/write services — rejected as over-engineering for a single-process application.
**Consequences:** The orchestrator combines Application Service (Fowler) + Process Manager (Hohpe & Woolf) roles. Repositories are injected via constructor (DI), never imported directly. Unit tests pass `None` for repos, integration tests use in-memory SQLite. Full rationale with references in `docs/ORCHESTRATION_DESIGN.md`.

## 2026-04-10 — YAML Agent Config (F06)

**Status:** accepted
**Context:** Agent prompts, retries, and tool bindings were hardcoded in Python. Changing a prompt required a code change and redeploy. For a platform serving multiple studies, clinical teams need to customize agent behavior per therapeutic area without touching code.
**Decision:** Externalize agent configuration to YAML files in `config/agents/`. A factory (`src/agents/factory.py`) loads them using type/tool registries (`src/agents/registry.py`). Python modules keep output types, deps dataclasses, and tool functions — only configuration moves to YAML.
**Alternatives considered:** (1) Pydantic Settings with env vars per agent — rejected because prompts are multi-line text, awkward in env vars. (2) JSON config — rejected because YAML is more readable for multi-line prompts (block scalar `|`). (3) Database-stored prompts — rejected as over-engineering for the current scope.
**Consequences:** Adding a new agent = create a YAML file + add types to registry. Per-study prompt variants = copy YAML, modify prompt, pass different config path. Trade-off: runtime error if YAML references unregistered type (caught by startup tests).

## 2026-04-13 — Long-Term Memory via `query_patterns` Tool + `save_patterns` Builtin (Phase 16.1)

**Status:** accepted
**Context:** `PatternRepository`, `FeedbackRepository`, and `QCHistoryRepository` existed with full CRUD methods but were never instantiated outside tests — the slides claimed "long-term memory" but nothing in the pipeline actually persisted or consumed it. Closing that gap needed two decisions: **when** does the pipeline write, and **how** does the coder agent read?

**Decision:** Two targeted additions, no new layer.

1. **Write path — new `save_patterns` builtin.** Runs *after* the `human_review` HITL gate and *before* `audit`, so only patterns that a human has validated get persisted. Iterates `ctx.dag.execution_order`, skips any node whose `status != DerivationStatus.APPROVED`, and writes one `PatternRow` + one `QCHistoryRow` per approved node. Deliberately **omitted from `express.yaml`** (no HITL = no human-validated patterns worth keeping). Commit happens once at the end of the step via `ctx.pattern_repo.commit()`.

2. **Read path — new `query_patterns` PydanticAI tool.** Accepts no args, pulls `variable_type` from `ctx.deps.rule.variable`, asks `PatternRepository.query_by_type(variable_type, limit=3)`, and returns up to 3 formatted patterns to the LLM. The coder's system prompt instructs it to call `query_patterns` **first**, adapt any good match, and fall back to generating from scratch only if nothing relevant is found. The QC programmer's prompt says it may call `query_patterns` too but MUST implement a *different* approach — maintaining QC independence.

**DI shape (critical for the pre-push hooks):** Repositories are constructed in `src/factory.py` (outside the `src/engine/` and `src/agents/` FORBIDDEN_LAYERS of `check_repo_direct_instantiation`) and injected via `PipelineContext.pattern_repo` and `CoderDeps.pattern_repo`. Both fields are typed under `TYPE_CHECKING` only so the engine layer never imports `sqlalchemy` at runtime (enforced by `check_raw_sql_in_engine`). `BaseRepository` grew a `commit()` helper so engine code can flush without touching the session directly.

**Alternatives considered:**
- **Vector embedding store (Chroma, pgvector).** Rejected for this homework: patterns are small (tens of rows per variable), exact-match lookup by variable name is sufficient, and adding a vector DB would introduce a second persistence surface for no measurable win at this scale. Worth revisiting when the pattern count crosses ~10k.
- **Write patterns immediately after coder+QC match (no HITL gate).** Rejected because unreviewed patterns would pollute the memory with auto-approved express-mode output. The Sanofi demo narrative is "human validates, machine learns" — writing before the human signs off undermines that.
- **Store session on `PipelineContext` and let the tool open its own transactions.** Tried first, got rejected by the `check_raw_sql_in_engine` pre-push hook (TYPE_CHECKING sqlalchemy imports in `src/engine/` trip the AST walker). The DI-injected repo pattern is strictly better — engine code never sees a session.

**Consequences:**
- Running the same spec twice now produces visible cache hits: the second run's `patterns` table has the rows from the first run, and the coder's LLM trace shows it calling `query_patterns` before writing code.
- Import-linter has 4 TYPE_CHECKING-only `ignore_imports` exceptions (`agents.deps → pattern_repo`, `engine.pipeline_context → pattern_repo`, `... → qc_history_repo`, `engine.derivation_runner → pattern_repo`) — each documented inline with the rationale.
- The `save_patterns` step adds a new dependency edge in the pipeline YAML, which forces a bump to the hardcoded step count in `test_pipeline_scenarios.py` and `test_pipeline_interpreter.py`. Worth doing because those tests now catch accidental step removals.
- End-to-end smoke test verified: two runs of `simple_mock.yaml` against the live backend produced `+2` rows per variable in the `patterns` table and `+8` rows in `qc_history` (one per approved variable per run), with fresh `approach` strings distinct from prior seeding data. The LTM loop is observably real, not just test-verified.

## 2026-04-13 — HITL Expansion: Depth Over Count (Phase 16.2)

**Status:** accepted
**Context:** Phase 12 shipped a single HITL gate (`human_review`) that just toggled a boolean — approve = continue, no approval = release the gate. The design doc and slides promised more: per-variable decisions, rejection with reason, and the ability to override a specific derivation. The naive implementation would have been "add more gates" (spec review gate → variable review gate → code override gate → final sign-off gate). We chose depth over count.

**Decision:** Keep **one** HITL gate in `clinical_derivation.yaml` — `human_review` — but give the reviewer **three distinct actions** at that gate, each with rich feedback, all persisted to `FeedbackRepository`:

1. **Approve with feedback** — optional per-variable `ApprovalRequest` payload. Reviewer can approve the whole workflow as-is (no body, backwards compat) or approve individual variables with per-variable notes. Each `VariableDecision` writes one `FeedbackRow`.
2. **Reject with mandatory reason** — `POST /workflows/{id}/reject` sets `ctx.rejection_requested = True` + `ctx.rejection_reason`, writes a workflow-level `FeedbackRow`, then releases the gate event. The `HITLGateStepExecutor` wakes from `event.wait()`, checks the flag, and raises `WorkflowRejectedError` — which inherits from `CDDEError → Exception` so the existing `_run_and_cleanup`'s `except Exception` catches it cleanly and the FSM transitions to FAILED via the existing fail path.
3. **Override approved code** — `POST /workflows/{id}/variables/{var}/override` runs the new `OverrideService`, which validates the variable exists, executes the new code via `execute_derivation`, applies the result to `ctx.derived_df` **only on success**, updates `node.approved_code`, records a `HUMAN_OVERRIDE` audit event, writes a `FeedbackRow`, and commits once. On failure the original `approved_code` is preserved and the router returns 400.

**Design rationale — why one deep gate, not four shallow ones:**

- **Cognitive cost per gate is high.** Every HITL gate forces a reviewer context switch, a UI render, and a decision-point — four gates means four interruptions. Clinical SMEs are expensive; their time is the bottleneck. One rich gate is cheaper to operate.
- **Four gates would need four UIs.** Each shallow gate means a new dialog, new endpoint, new state machine node, new integration tests. The total implementation cost scales with gate count, not with the value-per-gate.
- **The depth model matches how reviewers actually work.** A reviewer doesn't want to "approve the spec," then wait five minutes, then "approve the variables," then wait five minutes, then "sign off final output." They want to see everything in one pass and decide. The `ApprovalDialog` shows all variables with per-row checkboxes — the reviewer scans, unchecks anything that needs rework, and confirms once.
- **Enterprise pipeline keeps the deeper structure.** `enterprise.yaml` has 3 HITL gates (spec_approval, variable_review, final_signoff) precisely because 21 CFR Part 11 regulated environments may need stricter sign-off separation. The clinical_derivation pipeline is the "good enough for most teams" tier.

**Critical failure-mode decision — why `WorkflowRejectedError` and NOT `task.cancel()`:** Early design tried cancelling the running asyncio task on reject. `asyncio.CancelledError` inherits from `BaseException`, not `Exception`, so the existing `_run_and_cleanup`'s `except Exception` would miss it entirely, leaking the task and leaving the `WorkflowManager._running` dict in an inconsistent state. The flag-pattern solution stays strictly inside the `Exception` hierarchy — zero new error handling, zero new cleanup paths, just a new branch inside `HITLGateStepExecutor.execute` after `event.wait()` returns. One integration test (`test_reject_workflow_sets_flag_and_writes_feedback`) specifically verifies the FSM reaches FAILED cleanly via this path.

**Alternatives considered:**
- **Four shallow gates.** Rejected per the rationale above — scales poorly, annoys reviewers, quadruples the frontend surface. The enterprise pipeline keeps this option available when regulation demands it.
- **`task.cancel()` for rejection.** Rejected — `BaseException` inheritance breaks the existing cleanup path. Spent ~20 minutes figuring out why the FSM wouldn't fail cleanly before pivoting to the flag pattern.
- **No explicit override endpoint — just let the reviewer re-submit the whole workflow.** Rejected because re-running 8 LLM calls to fix one variable is economically absurd. The override path reuses the already-loaded `ctx` and just re-executes one pandas expression.

**Consequences:**
- `src/api/workflow_manager.py` hit the 230-line AST class-body limit. Extracted `approve_with_feedback_impl` and `reject_workflow_impl` into `src/api/workflow_hitl.py` and had `WorkflowManager` delegate — mirrors the earlier `workflow_lifecycle.py` extraction pattern.
- `src/api/routers/workflows.py` hit the 300-line file limit with 3 new endpoints. Split into `routers/hitl.py` for the HITL-specific endpoints.
- The frontend (Phase 16.3) ships 4 dialog components + 13 component tests. The `ApprovalDialog` and `CodeEditorDialog` had to use an inner-body-keyed-component pattern instead of `useEffect + setState` because the project's ESLint config bans `react-hooks/set-state-in-effect`. That pattern is idiomatic React but added 12 lines over the component-size spec target (still well under the hard cap).
- The `FeedbackRepository` is now actually used — before Phase 16.2, it existed only in unit tests and contributed zero to the running system. Every HITL action now feeds it, which makes the table useful for downstream analysis (trend of rejection reasons per study, etc.).
