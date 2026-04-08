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
