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

**Status:** accepted
**Context:** The orchestration workflow has 10 states and ~18 transitions, with audit requirements (every transition must be logged for 21 CFR Part 11 traceability). Initial plan used a hand-rolled dict + transition function (~15 lines).
**Decision:** Use `python-statemachine` v3.0 for the workflow FSM. Define states/transitions declaratively with `on_enter_state` callbacks for automatic logging and audit trail generation.
**Alternatives considered:** Hand-rolled `VALID_TRANSITIONS` dict with `transition()` function (simpler, no dependency). Rejected because audit logging on every transition would require manual `logger.info()` + `audit_records.append()` after every call — error-prone and repetitive.
**Consequences:** Small dependency (pure Python, no transitive deps). Transition callbacks handle audit logging declaratively. `.graph()` export available for panel presentation diagrams. FSM is independently testable. Trade-off: slightly more ceremony in class definition vs. a 15-line function.

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
