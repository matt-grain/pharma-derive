"""Formal FSM for the clinical derivation workflow using python-statemachine v3."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
from statemachine import State, StateMachine
from statemachine.exceptions import TransitionNotAllowed

__all__ = ["TransitionNotAllowed", "WorkflowFSM"]

from src.domain.models import AuditRecord


class WorkflowFSM(StateMachine):
    """Clinical derivation workflow state machine.

    States match WorkflowStep StrEnum values for consistency.
    """

    # --- States ---
    created = State(initial=True)
    spec_review = State()
    dag_built = State()
    deriving = State()
    verifying = State()
    debugging = State()
    review = State()
    auditing = State()
    completed = State(final=True)
    failed = State(final=True)

    # --- Transitions ---
    start_spec_review = created.to(spec_review)
    finish_spec_review = spec_review.to(dag_built)
    start_deriving = dag_built.to(deriving)
    start_verifying = deriving.to(verifying)
    next_variable = verifying.to(deriving)
    start_debugging = verifying.to(debugging)
    finish_review_from_verify = verifying.to(review)
    retry_from_debug = debugging.to(verifying)
    finish_review_from_debug = debugging.to(review)
    start_auditing = review.to(auditing)
    finish = auditing.to(completed)

    # Failure from any non-terminal state
    fail_from_created = created.to(failed)
    fail_from_spec_review = spec_review.to(failed)
    fail_from_dag_built = dag_built.to(failed)
    fail_from_deriving = deriving.to(failed)
    fail_from_verifying = verifying.to(failed)
    fail_from_debugging = debugging.to(failed)
    fail_from_review = review.to(failed)
    fail_from_auditing = auditing.to(failed)

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        self.audit_records: list[AuditRecord] = []
        super().__init__()  # type: ignore[no-untyped-call]  # python-statemachine stubs are incomplete

    def after_transition(self, source: State, target: State, event: str) -> None:
        """Log and record every state transition."""
        logger.info(
            "Workflow {wf_id}: {src} → {tgt} (via {evt})",
            wf_id=self.workflow_id,
            src=source.id,
            tgt=target.id,
            evt=event,
        )
        self.audit_records.append(
            AuditRecord(
                timestamp=datetime.now(UTC).isoformat(),
                workflow_id=self.workflow_id,
                variable="",
                action=f"state_transition:{target.id}",
                agent="orchestrator",
                details={"event": event, "from": source.id},
            )
        )

    def fail(self, error: str = "") -> None:
        """Transition to failed from any non-terminal state."""
        if error:
            logger.error("Workflow {wf_id} failing: {err}", wf_id=self.workflow_id, err=error)
        fail_transition = f"fail_from_{self.current_state_value}"
        getattr(self, fail_transition)()
