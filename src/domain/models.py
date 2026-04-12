"""Domain models for the Clinical Data Derivation Engine."""

from __future__ import annotations

from pydantic import BaseModel

# Re-exported for backward compatibility — callers that do
# `from src.domain.models import WorkflowStep` (etc.) continue to work.
from src.domain.enums import (  # noqa: F401
    AgentName,
    AuditAction,
    ConfidenceLevel,  # pyright: ignore[reportUnusedImport]
    CorrectImplementation,  # pyright: ignore[reportUnusedImport]
    DerivationStatus,
    OutputDType,
    QCVerdict,
    VerificationRecommendation,  # pyright: ignore[reportUnusedImport]
    WorkflowStep,  # pyright: ignore[reportUnusedImport]
)


class DerivationRule(BaseModel, frozen=True):
    """A single derivation from the transformation spec."""

    variable: str
    source_columns: list[str]
    logic: str
    output_type: OutputDType
    domain: str | None = None
    nullable: bool = True
    allowed_values: list[str] | None = None


class SpecMetadata(BaseModel, frozen=True):
    """Metadata from the transformation spec header."""

    study: str
    description: str
    version: str = "0.1.0"
    author: str = ""


class SourceConfig(BaseModel, frozen=True):
    """Source data configuration from the spec."""

    format: str
    path: str
    domains: list[str]
    primary_key: str = "USUBJID"


class SyntheticConfig(BaseModel, frozen=True):
    """Optional synthetic reference dataset config."""

    path: str | None = None
    rows: int = 15


class GroundTruthConfig(BaseModel, frozen=True):
    """Ground truth dataset for validation."""

    path: str
    format: str
    key: str


class ToleranceConfig(BaseModel, frozen=True):
    """Tolerance settings for numeric comparisons."""

    numeric: float = 0.0


class ValidationConfig(BaseModel, frozen=True):
    """Optional validation config."""

    ground_truth: GroundTruthConfig | None = None
    tolerance: ToleranceConfig = ToleranceConfig()


class TransformationSpec(BaseModel, frozen=True):
    """Complete transformation specification parsed from YAML."""

    metadata: SpecMetadata
    source: SourceConfig
    synthetic: SyntheticConfig = SyntheticConfig()
    validation: ValidationConfig = ValidationConfig()
    derivations: list[DerivationRule]


class DAGNode(BaseModel):
    """Enhanced DAG node — carries rule + execution provenance."""

    rule: DerivationRule
    status: DerivationStatus = DerivationStatus.PENDING
    layer: int = 0
    coder_code: str | None = None
    coder_approach: str | None = None
    qc_code: str | None = None
    qc_approach: str | None = None
    qc_verdict: QCVerdict | None = None
    debug_analysis: str | None = None
    approved_code: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None


class DerivationRunResult(BaseModel, frozen=True):
    """Atomic result of running coder + QC + verify + debug for one variable."""

    variable: str
    status: DerivationStatus
    coder_code: str | None = None
    coder_approach: str | None = None
    qc_code: str | None = None
    qc_approach: str | None = None
    qc_verdict: QCVerdict | None = None
    approved_code: str | None = None
    debug_analysis: str | None = None


class AuditRecord(BaseModel, frozen=True):
    """Immutable audit trail entry."""

    timestamp: str
    workflow_id: str
    variable: str
    # AuditAction | str — FSM concatenates f"{AuditAction.STATE_TRANSITION}:{target.id}" which is a plain str
    action: AuditAction | str
    agent: AgentName | str
    details: dict[str, str | int | float | bool | None] = {}


class PatternRecord(BaseModel, frozen=True):
    """A validated derivation pattern stored for cross-run reuse."""

    id: int
    variable_type: str
    spec_logic: str
    approved_code: str
    study: str
    approach: str
    created_at: str  # ISO 8601


class FeedbackRecord(BaseModel, frozen=True):
    """Human feedback on a derivation, stored for learning."""

    id: int
    variable: str
    feedback: str
    action_taken: str
    study: str
    created_at: str  # ISO 8601


class QCStats(BaseModel, frozen=True):
    """Aggregate QC statistics from historical runs."""

    total: int
    matches: int
    mismatches: int
    match_rate: float


class AuditSummary(BaseModel, frozen=True):
    """Structured output of the auditor agent."""

    study: str
    total_derivations: int
    auto_approved: int
    qc_mismatches: int
    human_interventions: int
    summary: str
    recommendations: list[str]
