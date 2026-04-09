"""Top-level workflow controller — drives the FSM and coordinates all steps."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pandas as pd  # noqa: TC002 — used in WorkflowState dataclass field at runtime
from pydantic import BaseModel

from src.agents.auditor import AuditorDeps, AuditSummary, auditor_agent
from src.audit.trail import AuditTrail
from src.domain.dag import DerivationDAG
from src.domain.models import AuditRecord, DerivationStatus, TransformationSpec
from src.domain.spec_parser import generate_synthetic, get_source_columns, load_source_data, parse_spec
from src.engine.derivation_runner import run_variable
from src.engine.llm_gateway import create_llm
from src.engine.workflow_fsm import WorkflowFSM

if TYPE_CHECKING:
    from src.persistence.repositories import (
        PatternRepository,
        QCHistoryRepository,
        WorkflowStateRepository,
    )


class WorkflowStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowState:
    """Mutable workflow state carried across orchestration steps."""

    workflow_id: str
    spec: TransformationSpec | None = None
    dag: DerivationDAG | None = None
    derived_df: pd.DataFrame | None = None
    synthetic_csv: str = ""
    current_variable: str | None = None
    errors: list[str] = field(default_factory=lambda: [])
    started_at: str | None = None
    completed_at: str | None = None


class WorkflowResult(BaseModel, frozen=True):
    """Immutable summary returned after a completed or failed run."""

    workflow_id: str
    study: str
    status: WorkflowStatus
    derived_variables: list[str]
    qc_summary: dict[str, str]
    audit_records: list[AuditRecord]
    audit_summary: AuditSummary | None = None
    errors: list[str]
    duration_seconds: float


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
        self._audit_trail.record(variable="", action="spec_parsed", agent="orchestrator")
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
            action="derivation_complete",
            agent="orchestrator",
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
        self._audit_trail.record(
            variable="",
            action="audit_complete",
            agent="auditor",
            details={"auto_approved": str(result.output.auto_approved)},
        )
        self._fsm.audit_records.append(
            AuditRecord(
                timestamp=datetime.now(UTC).isoformat(),
                workflow_id=self._state.workflow_id,
                variable="",
                action="audit_complete",
                agent="auditor",
                details={"auto_approved": str(result.output.auto_approved)},
            )
        )

    def _build_result(self, elapsed: float) -> WorkflowResult:
        dag = self._state.dag
        qc_summary: dict[str, str] = {}
        derived: list[str] = []
        if dag:
            for v, node in dag.nodes.items():
                qc_summary[v] = node.qc_verdict.value if node.qc_verdict else "pending"
                if node.status == DerivationStatus.APPROVED:
                    derived.append(v)

        status = WorkflowStatus.COMPLETED if self._fsm.current_state_value == "completed" else WorkflowStatus.FAILED
        study = self._state.spec.metadata.study if self._state.spec else "unknown"

        all_audit = self._audit_trail.records + self._fsm.audit_records
        return WorkflowResult(
            workflow_id=self._state.workflow_id,
            study=study,
            status=status,
            derived_variables=derived,
            qc_summary=qc_summary,
            audit_records=all_audit,
            errors=self._state.errors,
            duration_seconds=round(elapsed, 3),
        )
