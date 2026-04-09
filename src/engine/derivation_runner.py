"""Per-variable derivation runner — executes coder, QC, verify, and debug loop.

Extracted from orchestrator to keep each module under 200 lines.
Depends on agents/ and verification/ — called only from engine/.
"""

from __future__ import annotations

import asyncio
from io import StringIO
from typing import TYPE_CHECKING

import pandas as pd

from src.agents.debugger import DebugAnalysis, DebuggerDeps, debugger_agent
from src.agents.derivation_coder import DerivationCode, coder_agent
from src.agents.qc_programmer import qc_agent
from src.agents.tools import CoderDeps
from src.domain.models import DerivationStatus
from src.engine.llm_gateway import create_llm
from src.verification.comparator import VerificationResult, verify_derivation

if TYPE_CHECKING:
    from src.domain.dag import DerivationDAG

_MAX_DEBUG_RETRIES = 2


async def run_variable(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    synthetic_csv: str,
    llm_base_url: str,
) -> None:
    """Run coder + QC in parallel, verify, and debug if needed. Mutates dag and derived_df."""
    node = dag.get_node(variable)
    dag.update_node(variable, status=DerivationStatus.IN_PROGRESS)
    available = list(derived_df.columns)

    coder, qc_code = await _run_coder_and_qc(node.rule, derived_df, synthetic_csv, available, llm_base_url)
    dag.update_node(variable, coder_code=coder.python_code, qc_code=qc_code.python_code)

    vr = verify_derivation(variable, coder.python_code, qc_code.python_code, derived_df, available)

    if vr.verdict.value == "match":
        _apply_approved(variable, dag, derived_df, vr)
        return

    analysis = await _debug_variable(variable, dag, derived_df, vr, coder, qc_code, llm_base_url)
    dag.update_node(
        variable,
        debug_analysis=analysis.root_cause,
        status=DerivationStatus.QC_MISMATCH,
        qc_verdict=vr.verdict,
    )


async def _run_coder_and_qc(
    rule: object,
    df: pd.DataFrame,
    synthetic_csv: str,
    available: list[str],
    llm_base_url: str,
) -> tuple[DerivationCode, DerivationCode]:
    """Fan-out coder and QC agent calls in parallel."""
    from src.domain.models import DerivationRule  # local to avoid circular import at module level

    typed_rule: DerivationRule = rule  # type: ignore[assignment]
    llm = create_llm(base_url=llm_base_url)
    deps = CoderDeps(df=df, synthetic_csv=synthetic_csv, rule=typed_rule, available_columns=available)
    coder_out, qc_out = await asyncio.gather(
        coder_agent.run(str(typed_rule.logic), deps=deps, model=llm),
        qc_agent.run(str(typed_rule.logic), deps=deps, model=llm),
    )
    return coder_out.output, qc_out.output


def _apply_approved(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    vr: VerificationResult,
) -> None:
    """Mark node approved and add derived column to the working DataFrame."""
    dag.update_node(variable, qc_verdict=vr.verdict, status=DerivationStatus.APPROVED)
    approved_series: pd.Series[object] = pd.read_json(  # type: ignore[assignment]
        StringIO(vr.primary_result.series_json),  # type: ignore[arg-type]
        typ="series",
    )
    derived_df[variable] = approved_series


async def _debug_variable(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    vr: VerificationResult,
    coder: DerivationCode,
    qc_code: DerivationCode,
    llm_base_url: str,
) -> DebugAnalysis:
    """Run the debugger agent for a QC mismatch. Retry up to _MAX_DEBUG_RETRIES times."""
    node = dag.get_node(variable)
    summary = f"Mismatches: {vr.comparison.mismatch_count if vr.comparison else 'unknown'}"
    llm = create_llm(base_url=llm_base_url)
    result = await debugger_agent.run(
        f"Debug mismatch for {variable}",
        deps=DebuggerDeps(
            rule=node.rule,
            coder_code=coder.python_code,
            qc_code=qc_code.python_code,
            divergent_summary=summary,
            available_columns=list(derived_df.columns),
        ),
        model=llm,
    )
    return result.output
