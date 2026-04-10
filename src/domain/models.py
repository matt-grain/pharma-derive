"""Domain models for the Clinical Data Derivation Engine."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class OutputDType(StrEnum):
    """Valid output types for derivations — matches specs/TEMPLATE.md."""

    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CATEGORY = "category"


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


class QCVerdict(StrEnum):
    """Result of comparing primary and QC implementations."""

    MATCH = "match"
    MISMATCH = "mismatch"
    INSUFFICIENT_INDEPENDENCE = "insufficient_independence"


class WorkflowStep(StrEnum):
    """States in the workflow FSM."""

    CREATED = "created"
    SPEC_REVIEW = "spec_review"
    DAG_BUILT = "dag_built"
    DERIVING = "deriving"
    VERIFYING = "verifying"
    DEBUGGING = "debugging"
    REVIEW = "review"
    AUDITING = "auditing"
    COMPLETED = "completed"
    FAILED = "failed"


class DerivationStatus(StrEnum):
    """Status of a single derivation in the DAG."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    QC_PASS = "qc_pass"  # noqa: S105 — not a password; QC pass/fail status
    QC_MISMATCH = "qc_mismatch"
    APPROVED = "approved"
    FAILED = "failed"


class CorrectImplementation(StrEnum):
    """Debugger's assessment of which implementation is correct."""

    CODER = "coder"
    QC = "qc"
    NEITHER = "neither"


class ConfidenceLevel(StrEnum):
    """Debugger's confidence in its analysis."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class VerificationRecommendation(StrEnum):
    """Recommendation from the verification comparator."""

    NEEDS_DEBUG = "needs_debug"
    INSUFFICIENT_INDEPENDENCE = "insufficient_independence"
    AUTO_APPROVE = "auto_approve"


class AuditAction(StrEnum):
    """Actions recorded in the audit trail."""

    SPEC_PARSED = "spec_parsed"
    DERIVATION_COMPLETE = "derivation_complete"
    AUDIT_COMPLETE = "audit_complete"
    STATE_TRANSITION = "state_transition"


class AgentName(StrEnum):
    """Agent identifiers used in audit records."""

    ORCHESTRATOR = "orchestrator"
    CODER = "coder"
    QC_PROGRAMMER = "qc_programmer"
    DEBUGGER = "debugger"
    AUDITOR = "auditor"


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
    action: str
    agent: str
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


class WorkflowStatus(StrEnum):
    """Terminal workflow outcome — simplified from WorkflowStep."""

    COMPLETED = "completed"
    FAILED = "failed"
