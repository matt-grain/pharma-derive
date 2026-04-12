"""Base class and concrete executors for each StepType in a YAML-driven pipeline."""

from __future__ import annotations

import abc
import asyncio
from typing import TYPE_CHECKING, Any  # Any: load_agent returns Agent[Any, Any]

from loguru import logger

from src.domain.models import AgentName, AuditAction
from src.domain.pipeline_models import StepDefinition, StepType
from src.engine.step_builtins import BUILTIN_REGISTRY, build_agent_deps_and_prompt

if TYPE_CHECKING:
    from src.engine.pipeline_context import PipelineContext


class StepExecutor(abc.ABC):
    """Base class for pipeline step executors."""

    @abc.abstractmethod
    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        """Execute a pipeline step, reading from and writing to the context."""


class AgentStepExecutor(StepExecutor):
    """Runs a single PydanticAI agent. Used for spec_interpreter, auditor, etc."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        if step.agent is None:
            msg = f"Step '{step.id}' has type=agent but no 'agent' field"
            raise ValueError(msg)

        logger.info("Pipeline step '{step_id}': running agent '{agent}'", step_id=step.id, agent=step.agent)
        ctx.audit_trail.record(
            variable="",
            action=AuditAction.STEP_STARTED,
            agent=step.agent,  # guaranteed non-None: guard at line 31-33 ensures step.agent is set
            details={"step": step.id, "agent": step.agent},
        )

        # Import inside method to prevent circular imports at module load time
        from src.agents.factory import load_agent
        from src.config.llm_gateway import create_llm
        from src.config.settings import get_settings

        agent_dir = get_settings().agent_config_dir
        agent = load_agent(f"{agent_dir}/{step.agent}.yaml")
        llm = create_llm(base_url=ctx.llm_base_url)
        deps, prompt = build_agent_deps_and_prompt(step, ctx)
        result = await agent.run(prompt, deps=deps, model=llm)
        ctx.set_output(step.id, "result", result.output)

        ctx.audit_trail.record(
            variable="",
            action=AuditAction.STEP_COMPLETED,
            agent=step.agent,
            details={"step": step.id},
        )


class BuiltinStepExecutor(StepExecutor):
    """Runs a non-LLM Python function registered in BUILTIN_REGISTRY."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        if step.builtin is None:
            msg = f"Step '{step.id}' has type=builtin but no 'builtin' field"
            raise ValueError(msg)

        logger.info("Pipeline step '{step_id}': running builtin '{builtin}'", step_id=step.id, builtin=step.builtin)
        builtin_fn = BUILTIN_REGISTRY.get(step.builtin)
        if builtin_fn is None:
            msg = f"Unknown builtin '{step.builtin}'. Available: {list(BUILTIN_REGISTRY.keys())}"
            raise ValueError(msg)

        await builtin_fn(step, ctx)


class GatherStepExecutor(StepExecutor):
    """Runs N agents in parallel via asyncio.gather. Used for coder+QC."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        if not step.agents:
            msg = f"Step '{step.id}' has type=gather but no 'agents' list"
            raise ValueError(msg)

        logger.info(
            "Pipeline step '{step_id}': gathering {n} agents: {agents}",
            step_id=step.id,
            n=len(step.agents),
            agents=step.agents,
        )

        # Import inside method to prevent circular imports at module load time
        from src.agents.factory import load_agent
        from src.config.llm_gateway import create_llm
        from src.config.settings import get_settings

        agent_dir = get_settings().agent_config_dir
        llm = create_llm(base_url=ctx.llm_base_url)
        tasks: list[Any] = []  # Any: load_agent returns Agent[Any, Any] — coroutines are dynamically typed
        for agent_name in step.agents:
            agent = load_agent(f"{agent_dir}/{agent_name}.yaml")
            deps, prompt = build_agent_deps_and_prompt(step, ctx, agent_name=agent_name)
            tasks.append(agent.run(prompt, deps=deps, model=llm))

        results: list[Any] = list(await asyncio.gather(*tasks))  # Any: see tasks comment above
        for agent_name, result in zip(step.agents, results, strict=True):
            ctx.set_output(step.id, agent_name, result.output)  # type: ignore[union-attr]  # result is Any


class HITLGateStepExecutor(StepExecutor):
    """Pauses the pipeline until human approval via an asyncio.Event."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        message = str(step.config.get("message", "Awaiting human approval"))
        logger.info(
            "Pipeline step '{step_id}': HITL gate — {message}",
            step_id=step.id,
            message=message,
        )
        ctx.audit_trail.record(
            variable="",
            action=AuditAction.HITL_GATE_WAITING,
            agent=AgentName.ORCHESTRATOR,
            details={"step": step.id, "message": message},
        )

        # Store the event so external callers (API) can signal approval
        approval_event = asyncio.Event()
        ctx.set_output(step.id, "_approval_event", approval_event)
        await approval_event.wait()

        ctx.audit_trail.record(
            variable="",
            action=AuditAction.HUMAN_APPROVED,
            agent=AgentName.HUMAN,
            details={"gate": step.id},
        )


class ParallelMapStepExecutor(StepExecutor):
    """Iterates over DAG layers and runs derivation per layer via run_variable."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        if step.over != "dag_layers":
            msg = f"parallel_map only supports over='dag_layers', got '{step.over}'"
            raise ValueError(msg)
        if ctx.dag is None:
            msg = f"Step '{step.id}' requires ctx.dag but it is None"
            raise ValueError(msg)

        logger.info("Pipeline step '{step_id}': parallel_map over {over}", step_id=step.id, over=step.over)

        # Delegate to existing derivation runner — do NOT reimplement derivation logic here
        from src.engine.derivation_runner import run_variable

        coder_name = str(step.config.get("coder_agent", "coder"))
        qc_raw = step.config.get("qc_agent")
        debugger_raw = step.config.get("debugger_agent")
        qc_name: str | None = str(qc_raw) if qc_raw is not None else None
        debugger_name: str | None = str(debugger_raw) if debugger_raw is not None else None

        layers = ctx.dag.layers
        for layer in layers:
            await asyncio.gather(
                *[
                    run_variable(
                        variable=v,
                        dag=ctx.dag,
                        derived_df=ctx.derived_df,  # type: ignore[arg-type]  # ctx.dag non-None implies derived_df set
                        synthetic_csv=ctx.synthetic_csv,
                        llm_base_url=ctx.llm_base_url,
                        coder_agent_name=coder_name,
                        qc_agent_name=qc_name,
                        debugger_agent_name=debugger_name,
                    )
                    for v in layer
                ]
            )


STEP_EXECUTOR_REGISTRY: dict[StepType, StepExecutor] = {
    StepType.AGENT: AgentStepExecutor(),
    StepType.BUILTIN: BuiltinStepExecutor(),
    StepType.GATHER: GatherStepExecutor(),
    StepType.PARALLEL_MAP: ParallelMapStepExecutor(),
    StepType.HITL_GATE: HITLGateStepExecutor(),
}
