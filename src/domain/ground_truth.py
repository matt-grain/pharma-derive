"""Ground-truth comparison report for validating derivations against a reference ADaM dataset."""

from __future__ import annotations

from pydantic import BaseModel

from src.domain.models import QCVerdict  # noqa: TC001 — Pydantic needs QCVerdict at runtime for field validation


class VariableGroundTruthResult(BaseModel, frozen=True):
    """Comparison of a single derived variable against ground truth."""

    variable: str
    verdict: QCVerdict
    match_count: int
    mismatch_count: int
    total_rows: int
    mismatch_sample: list[str] = []  # first 5 divergent indices as strings (for display)
    error: str | None = None  # set when variable not in ground truth or comparison failed


class GroundTruthReport(BaseModel, frozen=True):
    """Full ground-truth comparison report attached to a workflow."""

    ground_truth_path: str
    total_variables: int
    matched_variables: int
    results: list[VariableGroundTruthResult]
