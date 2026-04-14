"""Domain enums for the Clinical Data Derivation Engine."""

from __future__ import annotations

from enum import StrEnum


class OutputDType(StrEnum):
    """Valid output types for derivations — matches specs/TEMPLATE.md."""

    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CATEGORY = "category"


class QCVerdict(StrEnum):
    """Result of comparing primary and QC implementations."""

    MATCH = "match"
    MISMATCH = "mismatch"
    INSUFFICIENT_INDEPENDENCE = "insufficient_independence"


class WorkflowStep(StrEnum):
    """States in the workflow FSM."""

    CREATED = "created"
    RUNNING = "running"  # background task accepted, pipeline executing
    SPEC_REVIEW = "spec_review"
    DAG_BUILT = "dag_built"
    DERIVING = "deriving"
    VERIFYING = "verifying"
    DEBUGGING = "debugging"
    REVIEW = "review"
    AUDITING = "auditing"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"  # workflow not found or state indeterminate


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
    HUMAN_APPROVED = "human_approved"
    HUMAN_OVERRIDE = "human_override"
    HUMAN_REJECTED = "human_rejected"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    HITL_GATE_WAITING = "hitl_gate_waiting"
    WORKFLOW_FAILED = "workflow_failed"
    CODER_PROPOSED = "coder_proposed"
    QC_VERDICT = "qc_verdict"
    DEBUGGER_RESOLVED = "debugger_resolved"


class AgentName(StrEnum):
    """Agent identifiers used in audit records."""

    ORCHESTRATOR = "orchestrator"
    CODER = "coder"
    QC_PROGRAMMER = "qc_programmer"
    DEBUGGER = "debugger"
    AUDITOR = "auditor"
    HUMAN = "human"
