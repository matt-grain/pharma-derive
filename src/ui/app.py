"""CDDE — Clinical Data Derivation Engine."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="CDDE", page_icon="\U0001f9ec", layout="wide")

from src.ui.theme import inject_theme  # noqa: E402 — must follow set_page_config

inject_theme()

# Sidebar
st.sidebar.markdown('<h1 class="cdde-title">CDDE</h1>', unsafe_allow_html=True)
st.sidebar.markdown(
    '<div class="cdde-meta">Clinical Data Derivation Engine<br>'
    "Agentic AI \u2022 Double Programming \u2022 Audit Trail</div>",
    unsafe_allow_html=True,
)

page = st.sidebar.radio("Navigation", ["Workflow", "Audit Trail"], label_visibility="collapsed")

if page == "Workflow":
    from src.ui.pages.workflow import render_workflow_page

    render_workflow_page()
elif page == "Audit Trail":
    from src.ui.pages.audit import render_audit_page

    render_audit_page()
