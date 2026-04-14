"""Pipeline interpreter: executes a PipelineDefinition in topological dependency order."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from src.domain.exceptions import CDDEError
from src.domain.models import AgentName, AuditAction

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.domain.pipeline_models import PipelineDefinition, StepDefinition
    from src.engine.pipeline_context import PipelineContext
    from src.engine.pipeline_fsm import PipelineFSM

    StepCheckpoint = Callable[[str], Awaitable[None]]


class PipelineInterpreter:
    """Reads a pipeline definition and executes steps in dependency order.

    The interpreter is a thin loop — all business logic lives in step executors.
    """

    def __init__(
        self,
        pipeline: PipelineDefinition,
        ctx: PipelineContext,
        fsm: PipelineFSM | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._ctx = ctx
        self._fsm = fsm
        self._execution_order = topological_sort(pipeline.steps)
        self._current_step: str | None = None
        self._completed_steps: list[StepDefinition] = []

    @property
    def current_step(self) -> str | None:
        """The ID of the currently executing step, or None if not started/finished."""
        return self._current_step

    @property
    def completed_steps(self) -> list[StepDefinition]:
        """Steps that have completed successfully so far in this run."""
        return list(self._completed_steps)

    @property
    def pipeline(self) -> PipelineDefinition:
        return self._pipeline

    async def run(self, on_step_complete: StepCheckpoint | None = None) -> None:
        """Execute all pipeline steps in topological order.

        If ``on_step_complete`` is supplied, it is awaited with the step id
        after each step finishes successfully. Used by the workflow manager
        to persist a checkpoint so in-flight runs survive a backend restart.
        A checkpoint failure must not abort the run — callers are responsible
        for catching their own errors.
        """
        logger.info(
            "Starting pipeline '{name}' ({n} steps)",
            name=self._pipeline.name,
            n=len(self._execution_order),
        )
        self._ctx.audit_trail.record(
            variable="",
            action=AuditAction.STEP_STARTED,
            agent=AgentName.ORCHESTRATOR,
            details={"pipeline": self._pipeline.name, "steps": ", ".join(s.id for s in self._execution_order)},
        )

        for step in self._execution_order:
            self._current_step = step.id
            if self._fsm is not None:
                self._fsm.advance(step.id)
            await self._execute_step(step)
            self._completed_steps.append(step)
            if on_step_complete is not None:
                await on_step_complete(step.id)

        self._current_step = None
        logger.info("Pipeline '{name}' completed successfully", name=self._pipeline.name)

    async def _execute_step(self, step: StepDefinition) -> None:
        """Execute a single step, dispatching to the correct executor."""
        from src.engine.step_executors import STEP_EXECUTOR_REGISTRY

        executor = STEP_EXECUTOR_REGISTRY.get(step.type)
        if executor is None:
            msg = f"No executor registered for step type '{step.type}'"
            raise CDDEError(msg)

        logger.info("Executing step '{step_id}' (type={type})", step_id=step.id, type=step.type)
        start = time.perf_counter()

        try:
            await executor.execute(step, self._ctx)
        except CDDEError:
            raise  # Domain errors propagate as-is
        except Exception as exc:
            msg = f"Step '{step.id}' failed: {exc}"
            raise CDDEError(msg) from exc

        elapsed = time.perf_counter() - start
        logger.info(
            "Step '{step_id}' completed in {elapsed:.2f}s",
            step_id=step.id,
            elapsed=elapsed,
        )


def topological_sort(steps: list[StepDefinition]) -> list[StepDefinition]:
    """Sort steps by dependency order. Raises CDDEError if cycle detected.

    Uses Kahn's algorithm (BFS-based topological sort).
    """
    step_map: dict[str, StepDefinition] = {s.id: s for s in steps}
    # Validate all depends_on references exist
    for step in steps:
        for dep in step.depends_on:
            if dep not in step_map:
                msg = f"Step '{step.id}' depends on unknown step '{dep}'"
                raise CDDEError(msg)

    # Build in-degree map
    in_degree: dict[str, int] = {s.id: 0 for s in steps}
    adjacency: dict[str, list[str]] = {s.id: [] for s in steps}
    for step in steps:
        for dep in step.depends_on:
            adjacency[dep].append(step.id)
            in_degree[step.id] += 1

    # BFS from nodes with zero in-degree
    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    result: list[StepDefinition] = []

    while queue:
        # Sort queue for deterministic ordering when multiple steps have zero in-degree
        queue.sort()
        current = queue.pop(0)
        result.append(step_map[current])
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(steps):
        msg = "Pipeline has circular dependencies"
        raise CDDEError(msg)

    return result
