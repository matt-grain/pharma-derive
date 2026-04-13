"""Per-variable derivation runner — executes coder, QC, verify, and debug loop.

Extracted from orchestrator to keep each module under 200 lines.
Depends on agents/ and verification/ — called only from engine/.
Debug loop lives in debug_runner.py.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.agents.deps import CoderDeps
from src.agents.factory import load_agent
from src.agents.types import (  # noqa: TC001 — used at runtime in function signatures
    DerivationCode,
)
from src.config.llm_gateway import create_llm
from src.domain.executor import execute_derivation
from src.domain.models import DerivationStatus, QCVerdict
from src.engine.debug_runner import (
    apply_series_to_df,
    build_run_result,
    handle_mismatch,
)
from src.verification.comparator import VerificationResult, verify_derivation

if TYPE_CHECKING:
    import pandas as pd

    from src.domain.dag import DerivationDAG
    from src.domain.models import DerivationRule
    from src.persistence.pattern_repo import PatternRepository


async def run_variable(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    synthetic_csv: str,
    llm_base_url: str,
    coder_agent_name: str = "coder",
    qc_agent_name: str | None = "qc_programmer",
    debugger_agent_name: str | None = "debugger",
    pattern_repo: PatternRepository | None = None,
) -> None:
    """Run coder + optional QC in parallel, verify, and debug if needed. Mutates dag and derived_df."""
    node = dag.get_node(variable)
    available = list(derived_df.columns)
    coder, qc_code = await _run_coder_and_qc(
        node.rule, derived_df, synthetic_csv, available, llm_base_url, coder_agent_name, qc_agent_name, pattern_repo
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
    await handle_mismatch(variable, dag, derived_df, coder, qc_code, vr, llm_base_url, debugger_name)


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
        result = build_run_result(
            variable,
            DerivationStatus.APPROVED,
            coder,
            coder,  # use coder as both sides when no QC
            QCVerdict.MATCH,
            approved_code=coder.python_code,
        )
        dag.apply_run_result(result)
        apply_series_to_df(variable, exec_result, derived_df)


def _approve_match(
    variable: str,
    dag: DerivationDAG,
    derived_df: pd.DataFrame,
    coder: DerivationCode,
    qc_code: DerivationCode,
    vr: VerificationResult,
) -> None:
    """QC match path: record approval and persist the derived series."""
    result = build_run_result(
        variable,
        DerivationStatus.APPROVED,
        coder,
        qc_code,
        vr.verdict,
        approved_code=coder.python_code,
    )
    dag.apply_run_result(result)
    apply_series_to_df(variable, vr.primary_result, derived_df)


async def _run_coder_and_qc(
    rule: DerivationRule,
    df: pd.DataFrame,
    synthetic_csv: str,
    available: list[str],
    llm_base_url: str,
    coder_name: str,
    qc_name: str | None,
    pattern_repo: PatternRepository | None = None,
) -> tuple[DerivationCode, DerivationCode | None]:
    """Fan-out coder and optional QC agent calls in parallel."""
    from src.config.settings import get_settings

    agent_dir = get_settings().agent_config_dir
    llm = create_llm(base_url=llm_base_url)
    coder = load_agent(f"{agent_dir}/{coder_name}.yaml")
    deps = CoderDeps(
        df=df, synthetic_csv=synthetic_csv, rule=rule, available_columns=available, pattern_repo=pattern_repo
    )

    if qc_name is None:
        coder_out = await coder.run(str(rule.logic), deps=deps, model=llm)
        return coder_out.output, None

    qc = load_agent(f"{agent_dir}/{qc_name}.yaml")
    coder_out, qc_out = await asyncio.gather(
        coder.run(str(rule.logic), deps=deps, model=llm),
        qc.run(str(rule.logic), deps=deps, model=llm),
    )
    return coder_out.output, qc_out.output
