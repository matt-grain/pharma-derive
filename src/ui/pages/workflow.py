"""Workflow page — start derivation runs and review results."""

from __future__ import annotations

import asyncio
import json
from glob import glob
from pathlib import Path

import streamlit as st

from src.config.settings import get_settings
from src.domain.models import QCVerdict, WorkflowStatus
from src.domain.workflow_models import WorkflowResult
from src.ui.theme import inject_theme, result_row, score_card, status_badge


def render_workflow_page() -> None:
    """Render the workflow page."""
    inject_theme()
    st.markdown('<h1 class="cdde-title">Derivation Workflow</h1>', unsafe_allow_html=True)

    # --- Spec selection ---
    spec_files = sorted(glob("specs/*.yaml"))
    if not spec_files:
        st.warning("No spec files found in specs/. Add a YAML spec to get started.")
        return
    selected_spec = st.selectbox("Transformation Spec", spec_files)

    # --- Configuration ---
    col1, col2 = st.columns(2)
    with col1:
        llm_url = st.text_input("LLM Base URL", value=get_settings().llm_base_url)
    with col2:
        output_dir = st.text_input("Output Directory", value="output")

    # --- Run button ---
    if st.button("\U0001f680 Start Derivation Run", type="primary"):
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        with st.spinner("Running derivation workflow..."):
            try:
                result = asyncio.run(_run_workflow(str(selected_spec), llm_url, output_path))
                st.session_state["workflow_result"] = result
                st.success(f"Workflow {result.workflow_id} completed with status: {result.status.value}")
            except Exception as exc:
                st.error(f"Workflow failed: {exc}")
                return

    # --- Results display ---
    result = st.session_state.get("workflow_result")
    if isinstance(result, WorkflowResult):
        _render_results(result)


async def _run_workflow(spec_path: str, llm_url: str, output_dir: Path) -> WorkflowResult:
    """Run the orchestrator with SQLite persistence."""
    from src.factory import create_orchestrator

    orch, session = await create_orchestrator(
        spec_path=spec_path,
        llm_base_url=llm_url,
        output_dir=output_dir,
    )
    try:
        result = await orch.run()
        await session.commit()
        return result
    finally:
        await session.close()


def _render_results(result: WorkflowResult) -> None:
    """Render workflow results with AgentLens styling."""
    variant = "pass" if result.status == WorkflowStatus.COMPLETED else "fail"
    st.markdown(score_card("Workflow Status", result.status.value.upper(), variant), unsafe_allow_html=True)

    st.markdown(
        f'<div class="cdde-meta">'
        f"<strong>Study:</strong> {result.study} \u00b7 "
        f"<strong>Duration:</strong> {result.duration_seconds}s \u00b7 "
        f"<strong>Variables:</strong> {len(result.derived_variables)}"
        f"</div>",
        unsafe_allow_html=True,
    )

    _render_qc_summary(result)
    _render_derived_variables(result)
    _render_audit_summary(result)
    _render_errors(result)
    _render_export(result)


def _render_qc_summary(result: WorkflowResult) -> None:
    """Render QC result cards in a column grid."""
    if not result.qc_summary:
        return
    st.markdown("### QC Results")
    cols = st.columns(min(len(result.qc_summary), 4))
    for i, (var, verdict) in enumerate(result.qc_summary.items()):
        v = "pass" if verdict == QCVerdict.MATCH.value else ("fail" if verdict == QCVerdict.MISMATCH.value else "warn")
        with cols[i % len(cols)]:
            st.markdown(result_row(var, verdict, "", v), unsafe_allow_html=True)


def _render_derived_variables(result: WorkflowResult) -> None:
    """Render expandable detail for each derived variable."""
    if not result.derived_variables:
        return
    st.markdown("### Derived Variables")
    for var in result.derived_variables:
        with st.expander(f"\U0001f4ca {var}"):
            verdict = result.qc_summary.get(var, "unknown")
            v = "pass" if verdict == QCVerdict.MATCH.value else "warn"
            st.markdown(status_badge(verdict, v), unsafe_allow_html=True)


def _render_audit_summary(result: WorkflowResult) -> None:
    """Render aggregate audit statistics."""
    if not result.audit_summary:
        return
    st.markdown("### Audit Summary")
    summary = result.audit_summary
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Derivations", summary.total_derivations)
    c2.metric("Auto-Approved", summary.auto_approved)
    c3.metric("QC Mismatches", summary.qc_mismatches)
    if summary.recommendations:
        st.markdown("**Recommendations:**")
        for rec in summary.recommendations:
            st.markdown(f"- {rec}")


def _render_errors(result: WorkflowResult) -> None:
    """Render any workflow errors."""
    if not result.errors:
        return
    st.markdown("### Errors")
    for err in result.errors:
        st.error(err)


def _render_export(result: WorkflowResult) -> None:
    """Render download buttons for audit trail export."""
    st.markdown("### Export")
    audit_json = [r.model_dump() for r in result.audit_records]
    st.download_button(
        "\U0001f4e5 Audit Trail (JSON)",
        json.dumps(audit_json, indent=2, default=str),
        "audit_trail.json",
        "application/json",
    )
