"""API request/response schemas — DTOs for the HTTP boundary."""

from __future__ import annotations

from pydantic import BaseModel


class WorkflowCreateRequest(BaseModel):
    spec_path: str
    llm_base_url: str | None = None


class WorkflowCreateResponse(BaseModel, frozen=True):
    workflow_id: str
    status: str
    message: str


class WorkflowStatusResponse(BaseModel, frozen=True):
    workflow_id: str
    status: str
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


class DAGNodeOut(BaseModel, frozen=True):
    variable: str
    status: str
    layer: int
    coder_code: str | None = None
    qc_code: str | None = None
    qc_verdict: str | None = None
    approved_code: str | None = None
    dependencies: list[str] = []


class HealthResponse(BaseModel, frozen=True):
    status: str
    version: str
    workflows_in_progress: int
