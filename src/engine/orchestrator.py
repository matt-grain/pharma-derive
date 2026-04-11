"""Top-level workflow controller — drives the FSM and coordinates all steps."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from src.agents.deps import AuditorDeps
from src.agents.factory import load_agent
from src.audit.trail import AuditTrail
from src.config.llm_gateway import create_llm
from src.config.settings import get_settings
from src.domain.dag import DerivationDAG
from src.domain.exceptions import CDDEError, WorkflowStateError
from src.domain.models import (
    AgentName,
    AuditAction,
    DerivationStatus,
    WorkflowStep,
)
from src.domain.source_loader import get_source_columns, load_source_data
from src.domain.spec_parser import parse_spec
from src.domain.synthetic import generate_synthetic
from src.domain.workflow_fsm import WorkflowFSM
from src.domain.workflow_models import WorkflowResult, WorkflowState
from src.engine.derivation_runner import run_variable
from src.engine.orchestrator_helpers import build_derivation_details, build_workflow_result, serialize_workflow_state

if TYPE_CHECKING:
    from src.persistence import (
        PatternRepository,
        QCHistoryRepository,
        WorkflowStateRepository,
    )


@dataclass
class OrchestratorRepos:
    """Optional repository dependencies for persistence."""

    pattern_repo: PatternRepository | None = None
    qc_repo: QCHistoryRepository | None = None
    state_repo: WorkflowStateRepository | None = None


class DerivationOrchestrator:
    """Orchestrates spec interpretation, derivation, QC, debugging, and audit."""

    def __init__(
        self,
        spec_path: str | Path,
        llm_base_url: str | None = None,
        repos: OrchestratorRepos | None = None,
        output_dir: Path | None = None,
    ) -> None:
        effective_repos = repos or OrchestratorRepos()
        self._spec_path = Path(spec_path)
        self._llm_base_url = llm_base_url or get_settings().llm_base_url
        self._pattern_repo = effective_repos.pattern_repo
        self._qc_repo = effective_repos.qc_repo
        self._state_repo = effective_repos.state_repo
        self._output_dir = output_dir
        self._fsm = WorkflowFSM(workflow_id=uuid4().hex[:8])
        self._state = WorkflowState(workflow_id=self._fsm.workflow_id)
        self._audit_trail = AuditTrail(self._fsm.workflow_id)
        self._approval_event = asyncio.Event()

    @property
    def state(self) -> WorkflowState:
        return self._state

    @property
    def fsm(self) -> WorkflowFSM:
        return self._fsm

    @property
    def audit_trail(self) -> AuditTrail:
        return self._audit_trail

    @property
    def awaiting_approval(self) -> bool:
        """True if the workflow is paused at the review gate waiting for human approval."""
        return self._fsm.current_state_value == WorkflowStep.REVIEW.value and not self._approval_event.is_set()

    def approve(self) -> None:
        """Release the HITL gate — workflow proceeds to audit step."""
        self._audit_trail.record(
            variable="", action=AuditAction.HUMAN_APPROVED, agent=AgentName.HUMAN, details={"gate": "review"}
        )
        self._approval_event.set()

    async def run(self) -> WorkflowResult:
        """Execute the full derivation workflow end-to-end."""
        start = time.perf_counter()
        self._state.started_at = datetime.now(UTC).isoformat()

        source_cols: list[str] = []
        try:
            await self._step_spec_review()
            await self._step_build_dag()
            # Snapshot source columns so we can roll back partial derivations on failure
            source_cols = list(self._state.derived_df.columns) if self._state.derived_df is not None else []
            await self._step_derive_all()
            self._fsm.finish_review_from_verify()
            # HITL gate: workflow pauses at review state until human approves
            logger.info("Workflow {wf_id} waiting for human approval", wf_id=self._state.workflow_id)
            await self._approval_event.wait()
            await self._step_audit()
            self._fsm.finish()
        except CDDEError as exc:
            logger.error("Workflow {wf_id} failed: {err}", wf_id=self._state.workflow_id, err=exc)
            self._state.errors.append(str(exc))
            self._rollback_derived_columns(source_cols)
            self._fsm.fail(str(exc))
        except Exception as exc:
            logger.exception("Workflow {wf_id} unexpected error", wf_id=self._state.workflow_id)
            self._state.errors.append(f"Unexpected: {exc}")
            self._rollback_derived_columns(source_cols)
            self._fsm.fail(str(exc))

        await self._persist_state()
        self._state.completed_at = datetime.now(UTC).isoformat()
        result = self._build_result(time.perf_counter() - start)

        if self._output_dir is not None:
            self._audit_trail.to_json(self._output_dir / f"{self._state.workflow_id}_audit.json")
            self._export_adam(self._output_dir)

        return result

    def _export_adam(self, output_dir: Path) -> None:
        """Save the derived DataFrame as CSV and Parquet for downstream consumption."""
        if self._state.derived_df is None:
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        wf_id, df = self._state.workflow_id, self._state.derived_df
        df.to_csv(output_dir / f"{wf_id}_adam.csv", index=False)
        df.to_parquet(output_dir / f"{wf_id}_adam.parquet", index=False, engine="pyarrow")
        logger.info(
            "ADaM output saved ({rows} rows, {cols} columns)",
            rows=len(df),
            cols=len(df.columns),
        )

    def _rollback_derived_columns(self, source_cols: list[str]) -> None:
        """Drop any columns added during derivation to prevent partial state leaking."""
        if self._state.derived_df is None or not source_cols:
            return
        added = [c for c in self._state.derived_df.columns if c not in source_cols]
        if added:
            logger.warning("Rolling back {n} partial derivations: {cols}", n=len(added), cols=added)
            self._state.derived_df.drop(columns=added, inplace=True)

    async def _persist_state(self) -> None:
        """Persist final workflow state to long-term memory."""
        if self._state_repo is None:
            return
        fsm_state = str(self._fsm.current_state_value or "unknown")  # fallback for None state
        state_json = serialize_workflow_state(self._state, fsm_state)
        await self._state_repo.save(
            workflow_id=self._state.workflow_id,
            state_json=state_json,
            fsm_state=fsm_state,
        )

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
        if self._state.spec is None:
            raise WorkflowStateError("spec", "build_dag")
        if self._state.derived_df is None:
            raise WorkflowStateError("derived_df", "build_dag")
        self._fsm.start_deriving()
        self._state.dag = DerivationDAG(
            self._state.spec.derivations,
            get_source_columns(self._state.derived_df),
        )

    async def _step_derive_all(self) -> None:
        if self._state.dag is None:
            raise WorkflowStateError("dag", "derive_all")
        layers = self._state.dag.layers
        for idx, layer in enumerate(layers):
            self._fsm.start_verifying()
            await asyncio.gather(*[self._derive_variable(v) for v in layer])
            # Persist outcomes sequentially AFTER parallel derivation completes
            # (SQLAlchemy async session cannot handle concurrent flush calls)
            for v in layer:
                await self._record_derivation_outcome(v)
            if idx < len(layers) - 1:
                self._fsm.next_variable()

    async def _derive_variable(self, variable: str) -> None:
        if self._state.dag is None:
            raise WorkflowStateError("dag", "derive_variable")
        if self._state.derived_df is None:
            raise WorkflowStateError("derived_df", "derive_variable")
        await run_variable(
            variable=variable,
            dag=self._state.dag,
            derived_df=self._state.derived_df,
            synthetic_csv=self._state.synthetic_csv,
            llm_base_url=self._llm_base_url,
        )

    async def _record_derivation_outcome(self, variable: str) -> None:
        """Record an audit entry and persist QC/pattern data for a derivation outcome."""
        if self._state.dag is None:
            raise WorkflowStateError("dag", "record_outcome")
        node = self._state.dag.get_node(variable)
        self._audit_trail.record(
            variable=variable,
            action=AuditAction.DERIVATION_COMPLETE,
            agent=AgentName.ORCHESTRATOR,
            details=build_derivation_details(node),
        )

        # Persist QC result to long-term memory
        if self._qc_repo is not None and node.qc_verdict is not None:
            await self._qc_repo.store(
                variable=variable,
                verdict=node.qc_verdict,
                coder_approach=node.coder_approach or "",
                qc_approach=node.qc_approach or "",
                study=self._state.spec.metadata.study if self._state.spec else "",
            )

        # Store approved pattern for future reuse
        if self._pattern_repo is not None and node.status == DerivationStatus.APPROVED and node.approved_code:
            await self._pattern_repo.store(
                variable_type=variable,
                spec_logic=node.rule.logic,
                approved_code=node.approved_code,
                study=self._state.spec.metadata.study if self._state.spec else "",
                approach=node.coder_approach or "",
            )

    async def _step_audit(self) -> None:
        if self._state.dag is None:
            raise WorkflowStateError("dag", "audit")
        if self._state.spec is None:
            raise WorkflowStateError("spec", "audit")
        self._fsm.start_auditing()
        dag_lines = [f"{v}: {self._state.dag.get_node(v).status}" for v in self._state.dag.execution_order]
        auditor = load_agent("config/agents/auditor.yaml")
        llm = create_llm(base_url=self._llm_base_url)
        result = await auditor.run(
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
            agent=auditor.name or "auditor",
            details={"auto_approved": str(result.output.auto_approved)},
        )

    def _build_result(self, elapsed: float) -> WorkflowResult:
        return build_workflow_result(self._state, self._fsm, self._audit_trail, elapsed)
