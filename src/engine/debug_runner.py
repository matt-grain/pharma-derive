"""Debug loop for QC mismatches — runs debugger agent, resolves approved code, applies fix.

Also owns the shared DataFrame/result helpers used by derivation_runner.
Extracted from derivation_runner to keep each module under 200 lines.
Called only from derivation_runner; depends on agents/ and domain/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from typing import TYPE_CHECKING

import pandas as pd

from src.agents.deps import DebuggerDeps
from src.agents.factory import load_agent
from src.agents.types import (  # noqa: TC001 — used at runtime in @dataclass fields and function signatures
    DebugAnalysis,
    DerivationCode,
)
from src.config.llm_gateway import create_llm
from src.domain.exceptions import DerivationError
from src.domain.executor import ExecutionResult, execute_derivation
from src.domain.models import CorrectImplementation, DerivationRunResult, DerivationStatus, QCVerdict

if TYPE_CHECKING:
    from src.domain.dag import DerivationDAG
    from src.verification.comparator import VerificationResult


@dataclass
class DebugContext:
    """Context for the debug loop — groups params to keep _debug_variable under 5 args."""

    variable: str
    coder: DerivationCode
    qc_code: DerivationCode
    llm_base_url: str
    debugger_agent_name: str = field(default="debugger")


# ---------------------------------------------------------------------------
# Shared helpers (used by both derivation_runner and this module)
# ---------------------------------------------------------------------------


def apply_series_to_df(variable: str, exec_result: ExecutionResult, derived_df: pd.DataFrame) -> None:
    """Deserialize approved series and add to working DataFrame."""
    if exec_result.series_json is None:
        raise DerivationError(variable, "Execution produced no result data")
    series: pd.Series[object] = pd.read_json(  # type: ignore[assignment]  # pandas stubs type as DataFrame|Series
        StringIO(exec_result.series_json),
        typ="series",
    )
    derived_df[variable] = series


def build_run_result(
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


# ---------------------------------------------------------------------------
# Debug loop
# ---------------------------------------------------------------------------


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
    from src.config.settings import get_settings

    node = dag.get_node(ctx.variable)
    summary = f"Mismatches: {vr.comparison.mismatch_count if vr.comparison else 'unknown'}"
    agent_dir = get_settings().agent_config_dir
    debugger = load_agent(f"{agent_dir}/{ctx.debugger_agent_name}.yaml")
    llm = create_llm(base_url=ctx.llm_base_url)
    result = await debugger.run(
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


def _apply_debug_fix(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    coder: DerivationCode,
    qc_code: DerivationCode,
    vr: VerificationResult,
    approved_code: str,
    root_cause: str,
) -> bool:
    """Execute the debugger's fix and approve if successful. Returns True on success."""
    exec_result = execute_derivation(derived_df, approved_code, list(derived_df.columns))
    if not (exec_result.success and exec_result.series_json):
        return False
    result = build_run_result(
        variable,
        DerivationStatus.APPROVED,
        coder,
        qc_code,
        vr.verdict,
        approved_code=approved_code,
        debug_analysis=root_cause,
    )
    dag.apply_run_result(result)
    apply_series_to_df(variable, exec_result, derived_df)
    return True


async def handle_mismatch(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    coder: DerivationCode,
    qc_code: DerivationCode,
    vr: VerificationResult,
    llm_base_url: str,
    debugger_agent_name: str,
) -> None:
    """Debug a QC mismatch, attempt fix, and update the DAG."""
    ctx = DebugContext(
        variable=variable,
        coder=coder,
        qc_code=qc_code,
        llm_base_url=llm_base_url,
        debugger_agent_name=debugger_agent_name,
    )
    analysis = await _debug_variable(ctx, dag, derived_df, vr)
    approved_code = _resolve_approved_code(analysis, coder, qc_code)
    fixed = approved_code and _apply_debug_fix(
        variable, dag, derived_df, coder, qc_code, vr, approved_code, analysis.root_cause
    )
    if fixed:
        return

    result = build_run_result(
        variable,
        DerivationStatus.QC_MISMATCH,
        coder,
        qc_code,
        vr.verdict,
        debug_analysis=analysis.root_cause,
    )
    dag.apply_run_result(result)
