"""Per-variable derivation runner — executes coder, QC, verify, and debug loop.

Extracted from orchestrator to keep each module under 200 lines.
Depends on agents/ and verification/ — called only from engine/.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import StringIO
from typing import TYPE_CHECKING

import pandas as pd

from src.agents.debugger import debugger_agent
from src.agents.deps import CoderDeps, DebuggerDeps
from src.agents.derivation_coder import coder_agent
from src.agents.qc_programmer import qc_agent
from src.agents.types import (  # noqa: TC001 — used at runtime in @dataclass fields and function signatures
    DebugAnalysis,
    DerivationCode,
)
from src.config.llm_gateway import create_llm
from src.domain.exceptions import DerivationError
from src.domain.executor import ExecutionResult, execute_derivation
from src.domain.models import CorrectImplementation, DerivationRunResult, DerivationStatus, QCVerdict
from src.verification.comparator import VerificationResult, verify_derivation

if TYPE_CHECKING:
    from src.domain.dag import DerivationDAG
    from src.domain.models import DerivationRule


@dataclass
class DebugContext:
    """Context for the debug loop — groups params to keep _debug_variable under 5 args."""

    variable: str
    coder: DerivationCode
    qc_code: DerivationCode
    llm_base_url: str


def _apply_series_to_df(variable: str, exec_result: ExecutionResult, derived_df: pd.DataFrame) -> None:
    """Deserialize approved series and add to working DataFrame."""
    if exec_result.series_json is None:
        raise DerivationError(variable, "Execution produced no result data")
    series: pd.Series[object] = pd.read_json(  # type: ignore[assignment]  # pandas stubs type as DataFrame|Series
        StringIO(exec_result.series_json),
        typ="series",
    )
    derived_df[variable] = series


def _build_run_result(
    variable: str,
    status: DerivationStatus,
    coder: DerivationCode,
    qc_code: DerivationCode,
    verdict: QCVerdict,
    approved_code: str | None = None,
    debug_analysis: str | None = None,
) -> DerivationRunResult:
    """Build a DerivationRunResult with shared coder/QC fields."""
    return DerivationRunResult(
        variable=variable,
        status=status,
        coder_code=coder.python_code,
        coder_approach=coder.approach,
        qc_code=qc_code.python_code,
        qc_approach=qc_code.approach,
        qc_verdict=verdict,
        approved_code=approved_code,
        debug_analysis=debug_analysis,
    )


async def run_variable(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    synthetic_csv: str,
    llm_base_url: str,
) -> None:
    """Run coder + QC in parallel, verify, and debug if needed. Mutates dag and derived_df."""
    node = dag.get_node(variable)
    available = list(derived_df.columns)

    coder, qc_code = await _run_coder_and_qc(node.rule, derived_df, synthetic_csv, available, llm_base_url)
    vr = verify_derivation(variable, coder.python_code, qc_code.python_code, derived_df, available)

    if vr.verdict == QCVerdict.MATCH:
        result = _build_run_result(
            variable,
            DerivationStatus.APPROVED,
            coder,
            qc_code,
            vr.verdict,
            approved_code=coder.python_code,
        )
        dag.apply_run_result(result)
        _apply_series_to_df(variable, vr.primary_result, derived_df)
        return

    await _handle_mismatch(variable, dag, derived_df, coder, qc_code, vr, llm_base_url)


async def _handle_mismatch(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    coder: DerivationCode,
    qc_code: DerivationCode,
    vr: VerificationResult,
    llm_base_url: str,
) -> None:
    """Debug a QC mismatch, attempt fix, and update the DAG."""
    ctx = DebugContext(variable=variable, coder=coder, qc_code=qc_code, llm_base_url=llm_base_url)
    analysis = await _debug_variable(ctx, dag, derived_df, vr)
    approved_code = _resolve_approved_code(analysis, coder, qc_code)

    if approved_code:
        exec_result = execute_derivation(derived_df, approved_code, list(derived_df.columns))
        if exec_result.success and exec_result.series_json:
            result = _build_run_result(
                variable,
                DerivationStatus.APPROVED,
                coder,
                qc_code,
                vr.verdict,
                approved_code=approved_code,
                debug_analysis=analysis.root_cause,
            )
            dag.apply_run_result(result)
            _apply_series_to_df(variable, exec_result, derived_df)
            return

    result = _build_run_result(
        variable,
        DerivationStatus.QC_MISMATCH,
        coder,
        qc_code,
        vr.verdict,
        debug_analysis=analysis.root_cause,
    )
    dag.apply_run_result(result)


async def _run_coder_and_qc(
    rule: DerivationRule,
    df: pd.DataFrame,
    synthetic_csv: str,
    available: list[str],
    llm_base_url: str,
) -> tuple[DerivationCode, DerivationCode]:
    """Fan-out coder and QC agent calls in parallel."""
    llm = create_llm(base_url=llm_base_url)
    deps = CoderDeps(df=df, synthetic_csv=synthetic_csv, rule=rule, available_columns=available)
    coder_out, qc_out = await asyncio.gather(
        coder_agent.run(str(rule.logic), deps=deps, model=llm),
        qc_agent.run(str(rule.logic), deps=deps, model=llm),
    )
    return coder_out.output, qc_out.output


def _resolve_approved_code(
    analysis: DebugAnalysis,
    coder: DerivationCode,
    qc_code: DerivationCode,
) -> str | None:
    """Pick the approved code based on debugger's recommendation."""
    if analysis.suggested_fix and analysis.suggested_fix.strip():
        return analysis.suggested_fix
    if analysis.correct_implementation == CorrectImplementation.CODER:
        return coder.python_code
    if analysis.correct_implementation == CorrectImplementation.QC:
        return qc_code.python_code
    return None


async def _debug_variable(
    ctx: DebugContext,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    vr: VerificationResult,
) -> DebugAnalysis:
    """Run the debugger agent for a QC mismatch."""
    node = dag.get_node(ctx.variable)
    summary = f"Mismatches: {vr.comparison.mismatch_count if vr.comparison else 'unknown'}"
    llm = create_llm(base_url=ctx.llm_base_url)
    result = await debugger_agent.run(
        f"Debug mismatch for {ctx.variable}",
        deps=DebuggerDeps(
            rule=node.rule,
            coder_code=ctx.coder.python_code,
            qc_code=ctx.qc_code.python_code,
            divergent_summary=summary,
            available_columns=list(derived_df.columns),
        ),
        model=llm,
    )
    return result.output
