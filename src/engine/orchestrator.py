"""Top-level workflow controller — drives the FSM and coordinates all steps."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from src.agents.auditor import AuditorDeps, auditor_agent
from src.audit.trail import AuditTrail
from src.domain.dag import DerivationDAG
from src.domain.models import (
    AgentName,
    AuditAction,
    AuditRecord,
    DerivationStatus,
    WorkflowStatus,
    WorkflowStep,
)
from src.domain.source_loader import get_source_columns, load_source_data
from src.domain.spec_parser import parse_spec
from src.domain.synthetic import generate_synthetic
from src.engine.derivation_runner import run_variable
from src.engine.llm_gateway import create_llm
from src.engine.workflow_fsm import WorkflowFSM
from src.engine.workflow_models import WorkflowResult, WorkflowState

if TYPE_CHECKING:
    from src.persistence.repositories import (
        PatternRepository,
        QCHistoryRepository,
        WorkflowStateRepository,
    )


class DerivationOrchestrator:
    """Orchestrates spec interpretation, derivation, QC, debugging, and audit."""

    def __init__(
        self,
        spec_path: str | Path,
        llm_base_url: str = "http://localhost:8650/v1",
        pattern_repo: PatternRepository | None = None,
        qc_repo: QCHistoryRepository | None = None,
        state_repo: WorkflowStateRepository | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._spec_path = Path(spec_path)
        self._llm_base_url = llm_base_url
        self._pattern_repo = pattern_repo
        self._qc_repo = qc_repo
        self._state_repo = state_repo
        self._output_dir = output_dir
        self._fsm = WorkflowFSM(workflow_id=uuid4().hex[:8])
        self._state = WorkflowState(workflow_id=self._fsm.workflow_id)
        self._audit_trail = AuditTrail(self._fsm.workflow_id)

    @property
    def state(self) -> WorkflowState:
        return self._state

    @property
    def fsm(self) -> WorkflowFSM:
        return self._fsm

    @property
    def audit_trail(self) -> AuditTrail:
        return self._audit_trail

    async def run(self) -> WorkflowResult:
        """Execute the full derivation workflow end-to-end."""
        start = time.perf_counter()
        self._state.started_at = datetime.now(UTC).isoformat()

        try:
            await self._step_spec_review()
            await self._step_build_dag()
            await self._step_derive_all()
            self._fsm.finish_review_from_verify()
            await self._step_audit()
            self._fsm.finish()
        except Exception as exc:
            logger.exception("Workflow {wf_id} failed: {err}", wf_id=self._state.workflow_id, err=exc)
            self._state.errors.append(str(exc))
            self._fsm.fail(str(exc))

        self._state.completed_at = datetime.now(UTC).isoformat()
        result = self._build_result(time.perf_counter() - start)

        if self._output_dir is not None:
            self._audit_trail.to_json(self._output_dir / f"{self._state.workflow_id}_audit.json")

        return result

    async def _step_spec_review(self) -> None:
        self._fsm.start_spec_review()
        self._state.spec = parse_spec(self._spec_path)
        source_df = load_source_data(self._state.spec)
        self._state.derived_df = source_df.copy()
        self._state.synthetic_csv = generate_synthetic(source_df, rows=self._state.spec.synthetic.rows).to_csv(
            index=False
        )
        self._audit_trail.record(variable="", action=AuditAction.SPEC_PARSED, agent=AgentName.ORCHESTRATOR)
        self._fsm.finish_spec_review()

    async def _step_build_dag(self) -> None:
        assert self._state.spec is not None
        assert self._state.derived_df is not None
        self._fsm.start_deriving()
        self._state.dag = DerivationDAG(
            self._state.spec.derivations,
            get_source_columns(self._state.derived_df),
        )

    async def _step_derive_all(self) -> None:
        assert self._state.dag is not None
        layers = self._state.dag.layers
        for idx, layer in enumerate(layers):
            self._fsm.start_verifying()
            await asyncio.gather(*[self._derive_variable(v) for v in layer])
            if idx < len(layers) - 1:
                self._fsm.next_variable()

    async def _derive_variable(self, variable: str) -> None:
        assert self._state.dag is not None
        assert self._state.derived_df is not None
        await run_variable(
            variable=variable,
            dag=self._state.dag,
            derived_df=self._state.derived_df,
            synthetic_csv=self._state.synthetic_csv,
            llm_base_url=self._llm_base_url,
        )
        self._record_derivation_outcome(variable)

    def _record_derivation_outcome(self, variable: str) -> None:
        """Record an audit entry for the derivation outcome of a variable."""
        assert self._state.dag is not None
        node = self._state.dag.get_node(variable)
        self._audit_trail.record(
            variable=variable,
            action=AuditAction.DERIVATION_COMPLETE,
            agent=AgentName.ORCHESTRATOR,
            details={
                "status": node.status.value,
                "qc_verdict": node.qc_verdict.value if node.qc_verdict else None,
            },
        )

    async def _step_audit(self) -> None:
        assert self._state.dag is not None
        assert self._state.spec is not None
        self._fsm.start_auditing()
        dag_lines = [f"{v}: {self._state.dag.get_node(v).status}" for v in self._state.dag.execution_order]
        llm = create_llm(base_url=self._llm_base_url)
        result = await auditor_agent.run(
            "Generate audit summary",
            deps=AuditorDeps(
                dag_summary="\n".join(dag_lines),
                workflow_id=self._state.workflow_id,
                spec_metadata=self._state.spec.metadata,
            ),
            model=llm,
        )
        self._state.audit_summary = result.output
        self._audit_trail.record(
            variable="",
            action=AuditAction.AUDIT_COMPLETE,
            agent=AgentName.AUDITOR,
            details={"auto_approved": str(result.output.auto_approved)},
        )
        self._fsm.audit_records.append(
            AuditRecord(
                timestamp=datetime.now(UTC).isoformat(),
                workflow_id=self._state.workflow_id,
                variable="",
                action=AuditAction.AUDIT_COMPLETE,
                agent=AgentName.AUDITOR,
                details={"auto_approved": str(result.output.auto_approved)},
            )
        )

    def _build_result(self, elapsed: float) -> WorkflowResult:
        dag = self._state.dag
        qc_summary: dict[str, str] = {}
        derived: list[str] = []
        if dag:
            for v, node in dag.nodes.items():
                qc_summary[v] = node.qc_verdict.value if node.qc_verdict else DerivationStatus.PENDING.value
                if node.status == DerivationStatus.APPROVED:
                    derived.append(v)

        is_completed = self._fsm.current_state_value == WorkflowStep.COMPLETED.value
        status = WorkflowStatus.COMPLETED if is_completed else WorkflowStatus.FAILED
        study = self._state.spec.metadata.study if self._state.spec else "unknown"

        all_audit = self._audit_trail.records + self._fsm.audit_records
        return WorkflowResult(
            workflow_id=self._state.workflow_id,
            study=study,
            status=status,
            derived_variables=derived,
            qc_summary=qc_summary,
            audit_records=all_audit,
            audit_summary=self._state.audit_summary,
            errors=self._state.errors,
            duration_seconds=round(elapsed, 3),
        )
