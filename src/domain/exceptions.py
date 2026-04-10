"""Domain-specific exceptions for the Clinical Data Derivation Engine."""

from __future__ import annotations


class CDDEError(Exception):
    """Base for all CDDE domain errors."""


class WorkflowStateError(CDDEError):
    """Raised when workflow state is missing or invalid for the current operation."""

    def __init__(self, field: str, step: str) -> None:
        self.field = field
        self.step = step
        super().__init__(f"Required state '{field}' is None at step '{step}'")


class DerivationError(CDDEError):
    """Raised when a derivation operation fails."""

    def __init__(self, variable: str, reason: str) -> None:
        self.variable = variable
        self.reason = reason
        super().__init__(f"Derivation failed for '{variable}': {reason}")


class RepositoryError(CDDEError):
    """Raised when a persistence operation fails."""

    def __init__(self, operation: str, detail: str) -> None:
        self.operation = operation
        self.detail = detail
        super().__init__(f"Repository error during '{operation}': {detail}")


class DAGError(CDDEError):
    """Raised for DAG structural errors (cycle, missing node, etc.)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
