"""Mutable state container passed between pipeline step executors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any  # Any: heterogeneous step outputs stored by key

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

    from src.audit.trail import AuditTrail
    from src.domain.dag import DerivationDAG
    from src.domain.models import TransformationSpec
    from src.persistence.pattern_repo import PatternRepository
    from src.persistence.qc_history_repo import QCHistoryRepository


@dataclass
class PipelineContext:
    """Shared mutable state passed through pipeline step execution.

    Each step reads its inputs from named keys and writes its outputs back.
    The context also carries cross-cutting concerns (audit trail, workflow ID).
    """

    workflow_id: str
    audit_trail: AuditTrail
    llm_base_url: str
    output_dir: Path | None = None
    pattern_repo: PatternRepository | None = None
    qc_history_repo: QCHistoryRepository | None = None
    rejection_requested: bool = False
    rejection_reason: str = ""

    # Step outputs — populated during execution
    spec: TransformationSpec | None = None
    source_df: pd.DataFrame | None = None
    derived_df: pd.DataFrame | None = None
    synthetic_csv: str = ""
    dag: DerivationDAG | None = None
    # SDTM column → domain code map, populated by parse_spec step.
    # Historic workflows loaded from DB will have an empty map — source_columns
    # will be empty in the DAG response for those (known limitation, acceptable for now).
    source_column_domains: dict[str, str] = field(default_factory=lambda: dict[str, str]())

    # Pipeline metadata
    # Any: step outputs are heterogeneous (DataFrames, specs, audit summaries, etc.)
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=lambda: dict[str, dict[str, Any]]())

    errors: list[str] = field(default_factory=lambda: list[str]())

    def set_output(self, step_id: str, key: str, value: object) -> None:
        """Store a named output from a step."""
        if step_id not in self.step_outputs:
            self.step_outputs[step_id] = {}
        self.step_outputs[step_id][key] = value

    def get_output(self, step_id: str, key: str) -> object:
        """Retrieve a named output from a previous step."""
        outputs = self.step_outputs.get(step_id)
        if outputs is None:
            msg = f"No outputs found for step '{step_id}'"
            raise KeyError(msg)
        if key not in outputs:
            msg = f"Output '{key}' not found in step '{step_id}'. Available: {list(outputs.keys())}"
            raise KeyError(msg)
        return outputs[key]
