# Refactoring Tracker — Phase 10: Production Hardening

Code review findings from manual audit. Each item maps to an evaluation criterion in the Sanofi homework rubric.

## Status Legend

- ⬜ Not started
- 🔧 In progress
- ✅ Fixed
- ❌ Won't fix (with rationale)

## Findings

| # | Category | Finding | Severity | Eval Criteria | Status | Phase |
|---|----------|---------|----------|--------------|--------|-------|
| R01 | **Exceptions** | `assert` used as runtime guards in `orchestrator.py`, `dag.py`. Replaced with `WorkflowStateError`, `DAGError`. | Critical | §9.7 Implementation Quality, §11.C Reliability | ✅ | 10.2 |
| R02 | **Exceptions** | Bare `except Exception` in `orchestrator.py:run()`. Split into `CDDEError` + `Exception` with `logger.exception`. Added `_rollback_derived_columns()` to drop partial derivations on failure. | High | §11.C Reliability | ✅ | 10.2 |
| R03 | **Repository** | Zero error handling in repos. `_flush()` wraps writes, `_execute()` wraps reads — both catch `OperationalError` → `RepositoryError`. `pool_pre_ping=True` + pool config for PostgreSQL. | High | §11.C Reliability, §10.D Failure Handling | ✅ | 10.2 |
| R04 | **DAG Fragility** | Manual `dag.update_node()` calls. Replaced with atomic `DerivationRunResult` → `dag.apply_run_result()`. `update_node` removed, `apply_run_result` uses clean `getattr`/`setattr` loop. | High | §9.7 Implementation Quality | ✅ | 10.2 |
| R05 | **Agent Metadata** | `AgentName.AUDITOR` hardcoded. All agents now have `name=` param; orchestrator uses `auditor_agent.name`. | Medium | §9.7 Implementation Quality | ✅ | 10.2 |
| R06 | **Tool Tracing** | Bare tool functions. Added `@traced_tool` decorator with loguru timing + error logging. | Medium | §10.H Observability, §9.7 Quality | ✅ | 10.2 |
| R07 | **Module Focus** | `tools.py` 190 lines. Split into `tools/` package: `sandbox.py`, `inspect_data.py`, `execute_code.py`, `tracing.py`. | Medium | §9.7 Implementation Quality | ✅ | 10.1 |
| R08 | **Module Focus** | `repositories.py` 176 lines. Split into 5 files with `BaseRepository`. | Medium | §9.7 Implementation Quality | ✅ | 10.1 |
| R09 | **Misplaced Modules** | `llm_gateway.py`, `logging.py` in `engine/`. Moved to `src/config/`. | Low | §9.7 Implementation Quality | ✅ | 10.1 |
| R10 | **Misplaced Modules** | `workflow_fsm.py`, `workflow_models.py` in `engine/`. Moved to `src/domain/`. | Low | §9.7 Implementation Quality | ✅ | 10.1 |
| R11 | **Config Duplication** | `DATABASE_URL` and `LLM_BASE_URL` duplicated. Consolidated into `src/config/constants.py`. `llm_gateway.py` now imports from constants (residual duplicate fixed). | Low | §9.7 Implementation Quality | ✅ | 10.3 |
| R12 | **Type Safety** | Missing type hints in `get_stats()`. Added `total: int`, `matches: int` annotations. | Low | §9.7 Implementation Quality | ✅ | 10.3 |
| R13 | **Docstrings** | Inconsistent coverage. Added docstrings to all public repo methods. | Low | §9.7 Implementation Quality | ✅ | 10.3 |
| R14 | **Ruff Config** | Stale S101 ignores. Removed; added T20, C4, RET rules. CPY001 skipped (overhead vs homework scope). | Low | §9.7 Implementation Quality | ✅ | 10.3 |
| R15 | **LLM Gateway** | Multiple `create_llm()` calls. Added module-level cache with `reset_llm_cache()` for tests. | Low | §9.7 Implementation Quality | ✅ | 10.3 |

## Future Items (Not in Phase 10)

These are larger architectural changes identified during review, tracked but deferred:

| # | Category | Finding | Notes |
|---|----------|---------|-------|
| F01 | **UI/API Split** | ✅ Done (Phase 11). FastAPI + FastMCP + React SPA + Docker Compose. | Service-separated architecture |
| F02 | **YAML-Driven Pipeline** | ✅ Done (Phase 14). PipelineInterpreter reads YAML, 5 step executors, 3 pipeline configs, wired into API. | §11.A Platform Thinking |
| F03 | **YAML-Driven FSM** | ✅ Done (Phase 14). PipelineFSM auto-generates states from pipeline step IDs. Old WorkflowFSM kept as reference. | Coupled with F02 |
| F04 | **Mermaid Diagrams** | ✅ Done. `scripts/generate_diagrams.py` — FSM state diagram + 2 sequence diagrams. | Presentation enhancement |
| F05 | **Exec Sandbox** | Token-based blocklist in `execute_code` is naive (`"import"` blocks `"important"`). AST-based check or subprocess sandbox would be more reliable. | Security hardening |
| F06 | **YAML Agent Definitions** | ✅ Done (Phase 12). Agent configs in `config/agents/*.yaml`, factory + registries in `src/agents/`. | §11.A Platform Thinking |
| F07 | **ADaM Data Output** | ✅ Done (Phase 13). Data preview API, Parquet export, frontend Data tab with collapsible schema, row numbers, sticky headers, download buttons. | Core deliverable |
| F08 | **HITL Quick Win** | Workflow pauses at `review` state before audit. `POST /approve` endpoint transitions to auditing. Frontend "Approve All" button. Demonstrates §5C requirement. | §5C HITL — assignment requirement |
| F09 | **Per-Variable HITL** | Each variable pauses after QC. User reviews code + verdict, approves or rejects. Rejected variables re-derive with feedback injected into agent prompt. | Production HITL |
| F10 | **Full HITL Gates** | 3 gates: spec review approval, per-variable approval, final sign-off. DB-backed polling, timeout, escalation. | Enterprise HITL |

## Phase 15 — PydanticAI Native Alignment (Post-Review, 2026-04-12)

After reading the latest PydanticAI docs (`https://pydantic.dev/docs/ai/llms.txt`) we identified several framework features we should either adopt, document why we don't, or prototype. Rationale: an AI-ML Lead audit should show we know what the framework gives us natively — we've composed deliberately, not in ignorance.

| # | Category | Finding | Severity | Eval Criteria | Status | Phase |
|---|----------|---------|----------|--------------|--------|-------|
| F11 | **UsageLimits in pipeline YAML** | PydanticAI ships `UsageLimits(response_tokens_limit, request_limit, tool_calls_limit)` passed to `agent.run(..., usage_limits=...)`, raising `UsageLimitExceeded`. The Debugger retry loop is exactly the runaway-cost risk this was built for. Expose as a step-level `usage_limits:` field in pipeline YAML; map to `UsageLimits(**fields)` in step_executors. Low effort, strong production cost-governance story. | Medium | §10.A Deployment Architecture, §11.C Reliability | ⬜ | 15 |
| F12 | **`Thinking` capability on Debugger** | PydanticAI exposes `capabilities=[Thinking(effort='high')]` for reasoning-heavy tasks. Our Debugger agent does root-cause analysis of Coder/QC mismatches — a reasoning-heavy task. Prototype on the debugger agent spec (YAML), measure mismatch resolution quality on CDISC pilot. Rollback if no quality delta. | Low | §9.7 Implementation Quality | ⬜ | 15 |
| F13 | **ADR: `Agent.from_file()` vs our YAML loader** | PydanticAI ships `Agent.from_file('agent.yaml')` with fields `model`, `instructions`, `capabilities`, `model_settings`, `deps_schema`, `output_schema`, `retries`, `tool_timeout`. Our `config/agents/*.yaml` + factory covers the same shape but adds CDDE-specific workflow bindings (pipeline step hooks, typed deps builders). Write an ADR documenting the delta and why we didn't migrate to `Agent.from_file()` wholesale. Option: future refactor to wrap `Agent.from_file()` + layer our extras on top. | Low | §9.7 Implementation Quality | ⬜ | 15 |
| F14 | **ADR: Why NOT `CodeExecutionTool`** | PydanticAI's `CodeExecutionTool` provides provider-side sandboxed code execution (Anthropic, OpenAI, Google, xAI, Bedrock). It runs on the provider's infra — which is incompatible with our data security architecture (clinical data must never leave the organizational perimeter). Our local `execute_code` tool + sandbox.py stays. Write a short ADR explicitly stating this trade-off. Resolves the F05 sandbox hardening discussion by reframing: we chose local isolation over remote sandboxing for regulatory reasons, not because we were unaware of the framework path. | Medium | §10.A Deployment, §11.D Regulatory | ⬜ | 15 |
| F15 | **PII redaction as a capability (defense-in-depth)** | PydanticAI documents PII redaction via a custom `AbstractCapability` subclass overriding `after_model_request` (and/or `before_model_request`). Our dual-dataset architecture (LLM prompts see schema + synthetic data only, local tools access real data and return aggregates) already makes PHI leakage structurally impossible. Add a `PIIRedactionGuardrail` capability as belt-and-suspenders: catches developer mistakes if someone accidentally passes real data into a prompt. Apply to all agents via the shared LLM gateway. | Medium | §11.D Regulatory, §5C HITL | ⬜ | 15 |
| F16 | **Evaluate `pydantic-ai-shields` toolkit** | Community package at `github.com/vstorm-co/pydantic-ai-shields` wraps the PydanticAI capabilities system with production-ready guardrails: `CostTracking(budget_usd=...)` (raises `BudgetExceededError`), `ToolGuard(blocked=[...], require_approval=[...], approval_callback=fn)` — basically a native HITL tool-approval primitive, `PromptInjection(sensitivity="high")`, `PiiDetector(detect=["email","ssn","credit_card"])`, `SecretRedaction()`, `AsyncGuardrail(timing="concurrent", cancel_on_failure=True)`. Several of these map directly to our regulatory requirements: `CostTracking` for budget enforcement, `ToolGuard` for HITL on dangerous tools (execute_code approval), `PiiDetector` as F15 implementation. Evaluate whether to adopt the package as a dependency OR rebuild the 2-3 we actually need natively (dependency hygiene tradeoff per `change-discipline.md`). | Medium | §11.C Reliability, §11.D Regulatory | ⬜ | 15 |

### Rejected / Not Applicable

- **`pydantic-ai-skills` (DougTrajano/pydantic-ai-skills)** — implements the Agent Skills specification for progressive skill discovery and loading. Designed for generalist agents that load domain knowledge on demand. Our architecture is the opposite: specialized agents per workflow step (coder, qc, debugger, auditor), each with a tight, static tool surface. Skills don't fit our model.

## Phase 16 — Test Infrastructure Gaps (Surfaced 2026-04-13)

Found while running TEST_PLAN_P16.md Test 5 (LTM cross-run). The patterns persistence + tool function are well tested in isolation, but there is no test that proves the coder agent **actually invokes** `query_patterns` during its reasoning loop. Phase 14.4 was supposed to introduce `TestModel`/`FunctionModel`-based agent execution tests but never landed (see comment at `tests/unit/test_step_executors.py:3-4`).

| # | Category | Finding | Severity | Eval Criteria | Status | Phase |
|---|----------|---------|----------|--------------|--------|-------|
| F17 | **LTM read-loop end-to-end smoke test** | No test exists that runs the coder agent with a mocked model and asserts the agent's tool-call sequence includes `query_patterns` before `final_result`. We have: (a) 5 unit tests for the tool function in `tests/unit/test_query_patterns_tool.py`, (b) the coder.yaml registers the tool + the system prompt instructs the agent to call it, (c) integration test `test_two_runs_of_same_spec_second_run_finds_patterns` proves cross-session persistence + direct tool invocation. **Missing:** a `TestModel`/`FunctionModel`-driven test that runs `coder_agent.run(...)` and verifies the captured spans include a `query_patterns` tool call. ~30-45 min: build a `FunctionModel` whose `function` returns `query_patterns()` on the first turn and `final_result(...)` on the second, run the agent, assert via `agent.run_sync().all_messages()` that both tool calls fired in order. Doesn't prove the *real* model would do this, but proves the wiring is end-to-end traversable, which is the load-bearing claim. | Medium | §11.C Reliability, §9.7 Implementation Quality | ⬜ | 17 |
| F18 | **Multi-turn mailbox driving (tool-use loop, not just final_result)** | The AgentLens mailbox proxy was designed for AI-driven multi-turn responses, not single-shot human canned answers. Our current usage pattern (TEST_PLAN_P16.md §0.5) always responds with a `final_result` tool call on the first poll, which collapses the agent's ReAct loop to a single round trip and bypasses every intermediate tool call (including `query_patterns`). **What we should do:** when an LLM client (Claude or another agent) drives the mailbox, it should respond with `query_patterns()` on the first turn, see the tool result come back as a new mailbox poll (the agent's *next* model.complete() with the tool result appended), and only THEN respond with `final_result(...)`. This would make `query_patterns` show up in the AgentLens trace JSON for any mailbox-driven workflow. Investigate: (a) does the AgentLens proxy already support multi-turn (i.e. does it park a *second* request after a non-final tool call?), (b) if yes, write a "Claude responder" script that does the right thing per turn instead of jumping straight to final_result, (c) update TEST_PLAN_P16.md §0.5 to document the multi-turn responder pattern as the recommended path for AI-driven testing. The single-turn shortcut would still be available for human responders who don't want to play the full ReAct loop. | Medium | §11.A Platform Thinking, §11.C Reliability | ⬜ | 17 |

These two items are intentionally complementary: F17 closes the gap with a deterministic unit/integration test, F18 closes the gap with a more realistic end-to-end test path that exercises the real PydanticAI ReAct loop without burning real LLM credits. Doing both gives belt-and-suspenders coverage of the LTM read side.
