"""Higher-level verification combining execution, comparison, and code independence checks.

Depends on domain/ only — never imports agents/ or engine/.
"""

from __future__ import annotations

import ast
from difflib import SequenceMatcher
from io import StringIO
from typing import Any

import pandas as pd
from pydantic import BaseModel

from src.domain.executor import ComparisonResult, ExecutionResult, compare_results, execute_derivation
from src.domain.models import QCVerdict, VerificationRecommendation


class VerificationResult(BaseModel, frozen=True):
    """Full double-programming verification result for one variable."""

    variable: str
    verdict: QCVerdict
    primary_result: ExecutionResult
    qc_result: ExecutionResult
    comparison: ComparisonResult | None = None
    ast_similarity: float = 0.0
    recommendation: VerificationRecommendation = VerificationRecommendation.AUTO_APPROVE


def compute_ast_similarity(code_a: str, code_b: str) -> float:
    """Compare two Python expressions via normalised AST dump. Returns 0.0-1.0."""
    try:
        ast_a = ast.dump(ast.parse(code_a))
        ast_b = ast.dump(ast.parse(code_b))
    except SyntaxError:
        return 0.0
    return SequenceMatcher(None, ast_a, ast_b).ratio()


def verify_derivation(
    variable: str,
    coder_code: str,
    qc_code: str,
    df: pd.DataFrame,
    available_columns: list[str],
    tolerance: float = 0.0,
    independence_threshold: float = 0.8,
) -> VerificationResult:
    """Execute both implementations and compare results.

    Returns MISMATCH if either fails or outputs differ.
    Returns INSUFFICIENT_INDEPENDENCE if outputs match but code is too similar.
    Returns MATCH otherwise.
    """
    primary_result = execute_derivation(df, coder_code, available_columns)
    qc_result = execute_derivation(df, qc_code, available_columns)

    if not primary_result.success or not qc_result.success:
        return VerificationResult(
            variable=variable,
            verdict=QCVerdict.MISMATCH,
            primary_result=primary_result,
            qc_result=qc_result,
            recommendation=VerificationRecommendation.NEEDS_DEBUG,
        )

    # pd.read_json with typ="series" returns Series but pandas-stubs types it as DataFrame | Series
    # StringIO wrapper avoids the literal-json deprecation warning in pandas >= 2.2
    primary_series: pd.Series[Any] = pd.read_json(  # type: ignore[assignment]
        StringIO(primary_result.series_json),  # type: ignore[arg-type]  # non-None when success=True
        typ="series",
    )
    qc_series: pd.Series[Any] = pd.read_json(  # type: ignore[assignment]
        StringIO(qc_result.series_json),  # type: ignore[arg-type]
        typ="series",
    )

    comparison = compare_results(variable, primary_series, qc_series, tolerance)  # type: ignore[arg-type]  # pd.read_json returns DataFrame|Series; we assign to Series[Any] above
    ast_sim = compute_ast_similarity(coder_code, qc_code)

    verdict, recommendation = _determine_verdict(comparison, ast_sim, independence_threshold)

    return VerificationResult(
        variable=variable,
        verdict=verdict,
        primary_result=primary_result,
        qc_result=qc_result,
        comparison=comparison,
        ast_similarity=ast_sim,
        recommendation=recommendation,
    )


def _determine_verdict(
    comparison: ComparisonResult,
    ast_sim: float,
    independence_threshold: float,
) -> tuple[QCVerdict, VerificationRecommendation]:
    """Map comparison + similarity to a final verdict and recommendation string."""
    if comparison.mismatch_count > 0:
        return QCVerdict.MISMATCH, VerificationRecommendation.NEEDS_DEBUG
    if ast_sim > independence_threshold:
        return QCVerdict.INSUFFICIENT_INDEPENDENCE, VerificationRecommendation.INSUFFICIENT_INDEPENDENCE
    return QCVerdict.MATCH, VerificationRecommendation.AUTO_APPROVE
