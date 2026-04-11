# Composition Layer — Why YAML-Driven Orchestration

## The Gap PydanticAI Leaves Open

PydanticAI provides excellent agent abstractions:
- Typed dependency injection via `RunContext[DepsType]`
- Structured output validation via Pydantic models
- Tool binding with automatic schema generation
- Multi-turn conversation with tool use
- Retry with exponential backoff

What PydanticAI does NOT provide:
- **Multi-agent orchestration** — no built-in way to sequence, parallelize, or conditionally route between agents
- **Workflow state management** — no FSM, no persistent state between agent calls
- **Human-in-the-loop gates** — no approval mechanism
- **Pipeline configuration** — composition is always Python code

This is by design. PydanticAI's documentation explicitly states it's an agent framework, not a workflow engine. The composition layer is the developer's responsibility.

## Why Not Use an Existing Orchestrator?

| Framework | Why Not |
|-----------|---------|
| **CrewAI** | `async_execution` has known bugs (PR #2466). `human_input` is CLI-only. Hierarchical process is unpredictable. Stringly-typed. |
| **LangGraph** | Heavy LangChain dependency. Graph-first, not agent-first. Would require rewriting all agents. |
| **Prefect / Airflow** | Designed for data pipelines, not LLM agent orchestration. No native HITL or agent abstractions. |
| **Temporal** | Production-grade but massive infrastructure overhead for a homework project. |

## Our Approach: Thin YAML Composition Layer

Instead of adopting a framework, we built a ~120-line interpreter (`src/engine/pipeline_interpreter.py`) that:
1. **Reads pipeline YAML** — steps, dependencies, composition types
2. **Topologically sorts steps** — respects `depends_on` edges via Kahn's algorithm
3. **Dispatches to typed executors** — each `StepType` has a dedicated executor class in `step_executors.py`
4. **Passes context between steps** — typed `PipelineContext` dataclass holds shared mutable state
5. **Wraps exceptions** — non-`CDDEError` exceptions are caught and re-raised as `CDDEError` with step context

### Composition Primitives

| Type | PydanticAI Equivalent | Our Layer |
|------|----------------------|-----------|
| Single agent call | `agent.run()` | `AgentStepExecutor` |
| Parallel agents | `asyncio.gather(a.run(), b.run())` | `GatherStepExecutor` |
| Map over collection | Manual `for` loop | `ParallelMapStepExecutor` |
| Non-LLM function | Plain Python | `BuiltinStepExecutor` |
| Human approval | Not supported | `HITLGateStepExecutor` |

### Trade-offs

**What we gain:**
- Clinical teams can customize pipelines without Python changes
- New studies can skip QC (rapid prototyping) or add extra gates (enterprise compliance)
- Pipeline diagram auto-generated from YAML for regulatory presentations
- FSM states derivable from pipeline — no drift between pipeline and state machine

**What we accept:**
- Step executors still contain Python logic (agent deps building, DAG construction)
- Not a general-purpose workflow engine — pharma-specific composition types
- No dynamic branching mid-execution (pipeline is fixed at start)

## Comparison to CrewAI YAML

CrewAI also supports YAML configuration, but at a different level:

| Concern | CrewAI YAML | CDDE Pipeline YAML |
|---------|-------------|-------------------|
| Agent definition | role, goal, backstory | name, system_prompt, tools, retries |
| Task definition | description, agent, tools | step id, type, agent, config |
| Orchestration | Hardcoded Process class | Configurable step graph with depends_on |
| Parallelism | Buggy async_execution flag | `gather` and `parallel_map` primitives |
| HITL gates | CLI stdin only | `hitl_gate` step with web UI integration |
| FSM | None | Auto-generated from pipeline steps |
