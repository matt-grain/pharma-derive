"""API request/response schemas — DTOs for the HTTP boundary."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowCreateRequest(BaseModel, frozen=True):
    spec_path: str
    llm_base_url: str | None = None


class WorkflowCreateResponse(BaseModel, frozen=True):
    workflow_id: str
    status: str
    message: str


class WorkflowStatusResponse(BaseModel, frozen=True):
    workflow_id: str
    status: str
    study: str | None = None
    awaiting_approval: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    derived_variables: list[str] = []
    errors: list[str] = []


class WorkflowResultResponse(BaseModel, frozen=True):
    workflow_id: str
    study: str
    status: str
    derived_variables: list[str]
    qc_summary: dict[str, str]
    audit_summary: dict[str, object] | None = None
    errors: list[str]
    duration_seconds: float


class AuditRecordOut(BaseModel, frozen=True):
    timestamp: str
    workflow_id: str
    variable: str
    action: str
    agent: str
    details: dict[str, str | int | float | bool | None] = {}


class SpecListItem(BaseModel, frozen=True):
    filename: str
    study: str
    description: str
    derivation_count: int


class SourceColumnOut(BaseModel, frozen=True):
    """SDTM source column that feeds a derivation — used for lineage traceability (ADaM IG §2.6)."""

    name: str  # SDTM column name, e.g. "AGE", "RFXSTDTC"
    domain: str  # SDTM domain code (lowercase per CDISC convention), e.g. "dm", "ex"


class DAGNodeOut(BaseModel, frozen=True):
    variable: str
    status: str
    layer: int
    coder_code: str | None = None
    qc_code: str | None = None
    qc_verdict: str | None = None
    approved_code: str | None = None
    dependencies: list[str] = []
    source_columns: list[SourceColumnOut] = []  # SDTM columns this derivation reads directly


class ColumnInfo(BaseModel, frozen=True):
    """Column metadata for data preview."""

    name: str
    dtype: str
    null_count: int
    sample_values: list[str | int | float | None]


class DatasetPreview(BaseModel, frozen=True):
    """Preview of a single dataset (source or derived)."""

    label: str
    row_count: int
    column_count: int
    columns: list[ColumnInfo]
    rows: list[dict[str, str | int | float | None]]


class DataPreviewResponse(BaseModel, frozen=True):
    """Response for the data preview endpoint — source + derived side-by-side."""

    workflow_id: str
    source: DatasetPreview | None = None
    derived: DatasetPreview | None = None
    derived_formats: list[str] = []


class PipelineStepOut(BaseModel, frozen=True):
    """A single step in the pipeline definition."""

    id: str
    type: str
    description: str
    agent: str | None = None
    agents: list[str] | None = None
    builtin: str | None = None
    depends_on: list[str] = []
    config: dict[str, str | int | float | bool | list[str]] = {}
    has_sub_steps: bool = False


class PipelineOut(BaseModel, frozen=True):
    """Pipeline definition for the frontend diagram."""

    name: str
    version: str
    description: str
    steps: list[PipelineStepOut]


class HealthResponse(BaseModel, frozen=True):
    status: str
    version: str
    workflows_in_progress: int


class VariableDecision(BaseModel, frozen=True):
    """Per-variable approval decision from the human reviewer."""

    variable: str
    approved: bool
    note: str | None = None


class ApprovalRequest(BaseModel, frozen=True):
    """Optional payload for POST /approve — defaults to approve-all if omitted."""

    variables: list[VariableDecision] = []
    reason: str | None = None


class RejectionRequest(BaseModel, frozen=True):
    """Required payload for POST /reject."""

    reason: str = Field(min_length=1)


class VariableOverrideRequest(BaseModel, frozen=True):
    """Payload for POST /variables/{var}/override."""

    new_code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
