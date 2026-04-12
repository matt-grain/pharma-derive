"""Lightweight FSM tracker derived from pipeline step IDs."""

from __future__ import annotations

from src.domain.models import WorkflowStep


class PipelineFSM:
    """State tracker whose states are generated from the pipeline definition.

    States: 'created' → step IDs in order → 'completed' or 'failed'.
    Unlike WorkflowFSM, states are not hardcoded — they come from the YAML.
    """

    def __init__(self, workflow_id: str, step_ids: list[str]) -> None:
        self.workflow_id = workflow_id
        self._step_ids = step_ids
        self._current: str = WorkflowStep.CREATED.value
        self._failed: bool = False

    @property
    def current_state_value(self) -> str:
        return self._current

    def advance(self, step_id: str) -> None:
        """Move to a step's in-progress state."""
        self._current = step_id

    def complete(self) -> None:
        """Mark the pipeline as completed."""
        self._current = WorkflowStep.COMPLETED.value

    def fail(self, error: str = "") -> None:
        """Mark the pipeline as failed."""
        self._current = WorkflowStep.FAILED.value
        self._failed = True

    @property
    def is_terminal(self) -> bool:
        return self._current in (WorkflowStep.COMPLETED.value, WorkflowStep.FAILED.value)

    @property
    def is_failed(self) -> bool:
        return self._failed
