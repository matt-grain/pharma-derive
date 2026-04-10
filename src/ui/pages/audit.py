"""Audit trail page — view and export completed run audit records."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.ui.theme import inject_theme, result_row


def _render_records(records: list[dict[str, str]], var_filter: list[str]) -> None:
    """Render filtered audit records."""
    filtered = [r for r in records if not var_filter or r.get("variable") in var_filter]
    st.markdown(f'<div class="cdde-meta">Records: {len(filtered)} / {len(records)}</div>', unsafe_allow_html=True)
    for record in filtered:
        variant = "pass" if "complete" in record.get("action", "") else "info"
        st.markdown(
            result_row(
                record.get("variable", "\u2014"),
                record.get("action", ""),
                f"{record.get('agent', '')} \u00b7 {record.get('timestamp', '')}",
                variant,
            ),
            unsafe_allow_html=True,
        )


def render_audit_page() -> None:
    """Render the audit trail viewer page."""
    inject_theme()
    st.markdown('<h1 class="cdde-title">Audit Trail</h1>', unsafe_allow_html=True)

    output_dir = Path("output")
    if not output_dir.exists():
        st.info("No output directory found. Run a workflow first.")
        return

    audit_files = sorted(output_dir.glob("*_audit.json"), reverse=True)
    if not audit_files:
        st.info("No audit trail files found. Run a workflow to generate one.")
        return

    selected: str = st.selectbox("Select Run", [f.stem for f in audit_files])
    audit_path = output_dir / f"{selected}.json"
    records: list[dict[str, str]] = json.loads(audit_path.read_text())

    # Filter by variable
    variables = sorted({r["variable"] for r in records if r.get("variable")})
    var_filter: list[str] = st.multiselect("Filter by Variable", variables)

    _render_records(records, var_filter)

    st.download_button(
        "\U0001f4e5 Download Full Audit",
        json.dumps(records, indent=2, default=str),
        f"{selected}.json",
        "application/json",
    )
