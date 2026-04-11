"""Per-variable derivation runner — executes coder, QC, verify, and debug loop.

Extracted from orchestrator to keep each module under 200 lines.
Depends on agents/ and verification/ — called only from engine/.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from io import StringIO
from typing import TYPE_CHECKING

import pandas as pd

from src.agents.deps import CoderDeps, DebuggerDeps
from src.agents.factory import load_agent
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
    debugger_agent_name: str = field(default="debugger")


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
    coder_agent_name: str = "coder",
    qc_agent_name: str | None = "qc_programmer",
    debugger_agent_name: str | None = "debugger",
) -> None:
    """Run coder + optional QC in parallel, verify, and debug if needed. Mutates dag and derived_df."""
    node = dag.get_node(variable)
    available = list(derived_df.columns)
    coder, qc_code = await _run_coder_and_qc(
        node.rule, derived_df, synthetic_csv, available, llm_base_url, coder_agent_name, qc_agent_name
    )

    if qc_code is None:
        # Express mode — no QC, auto-approve coder output directly
        _approve_no_qc(variable, dag, derived_df, coder, available)
        return

    vr = verify_derivation(variable, coder.python_code, qc_code.python_code, derived_df, available)
    if vr.verdict == QCVerdict.MATCH:
        _approve_match(variable, dag, derived_df, coder, qc_code, vr)
        return

    debugger_name = debugger_agent_name or "debugger"
    await _handle_mismatch(variable, dag, derived_df, coder, qc_code, vr, llm_base_url, debugger_name)


def _approve_no_qc(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    coder: DerivationCode,
    available: list[str],
) -> None:
    """Express mode: execute and approve the coder output directly (no QC)."""
    exec_result = execute_derivation(derived_df, coder.python_code, available)
    if exec_result.success:
        result = _build_run_result(
            variable,
            DerivationStatus.APPROVED,
            coder,
            coder,  # use coder as both sides when no QC
            QCVerdict.MATCH,
            approved_code=coder.python_code,
        )
        dag.apply_run_result(result)
        _apply_series_to_df(variable, exec_result, derived_df)


def _approve_match(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    coder: DerivationCode,
    qc_code: DerivationCode,
    vr: VerificationResult,
) -> None:
    """QC match path: record approval and persist the derived series."""
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


async def _handle_mismatch(
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

    result = _build_run_result(
        variable,
        DerivationStatus.QC_MISMATCH,
        coder,
        qc_code,
        vr.verdict,
        debug_analysis=analysis.root_cause,
    )
    dag.apply_run_result(result)


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
    result = _build_run_result(
        variable,
        DerivationStatus.APPROVED,
        coder,
        qc_code,
        vr.verdict,
        approved_code=approved_code,
        debug_analysis=root_cause,
    )
    dag.apply_run_result(result)
    _apply_series_to_df(variable, exec_result, derived_df)
    return True


async def _run_coder_and_qc(
    rule: DerivationRule,
    df: pd.DataFrame,
    synthetic_csv: str,
    available: list[str],
    llm_base_url: str,
    coder_name: str,
    qc_name: str | None,
) -> tuple[DerivationCode, DerivationCode | None]:
    """Fan-out coder and optional QC agent calls in parallel."""
    from src.config.settings import get_settings

    agent_dir = get_settings().agent_config_dir
    llm = create_llm(base_url=llm_base_url)
    coder = load_agent(f"{agent_dir}/{coder_name}.yaml")
    deps = CoderDeps(df=df, synthetic_csv=synthetic_csv, rule=rule, available_columns=available)

    if qc_name is None:
        coder_out = await coder.run(str(rule.logic), deps=deps, model=llm)
        return coder_out.output, None

    qc = load_agent(f"{agent_dir}/{qc_name}.yaml")
    coder_out, qc_out = await asyncio.gather(
        coder.run(str(rule.logic), deps=deps, model=llm),
        qc.run(str(rule.logic), deps=deps, model=llm),
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
