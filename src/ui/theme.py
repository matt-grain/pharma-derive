"""CDDE design system — AgentLens-inspired dark theme for Streamlit."""

from __future__ import annotations

import streamlit as st

_FONTS = (
    '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600'
    '&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">'
)

_CSS = """
<style>
:root {
  --bg-deep: #101114; --bg-surface: #16181c; --bg-elevated: #1e2025;
  --border: #363840; --text-primary: #f0f1f3; --text-secondary: #c2c4c9;
  --text-muted: #7d808a; --accent: #E86F33; --accent-dim: rgba(232,111,51,0.22);
  --success: #3ecf8e; --warning: #f0b429; --danger: #ef4444; --blue: #60a5fa;
}
.stApp { background-color: var(--bg-deep) !important; }
.stApp, .stMarkdown, .stText { color: var(--text-secondary) !important; }
h1, h2, h3 { color: var(--text-primary) !important; }
.cdde-title { font-family: 'Playfair Display', Georgia, serif; color: #E86F33 !important; }
.cdde-mono { font-family: 'IBM Plex Mono', monospace; }
.cdde-meta { font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: #7d808a;
  border-left: 2px solid rgba(232,111,51,0.22); padding-left: 0.75rem; margin-bottom: 1.5rem; }
.cdde-card { background: #1e2025; border-radius: 0.625rem; padding: 1rem 1.25rem;
  border: 1px solid #363840; border-left: 3px solid #7d808a; margin-bottom: 0.5rem; }
.cdde-card.pass { border-left-color: #3ecf8e; }
.cdde-card.warn { border-left-color: #f0b429; }
.cdde-card.fail { border-left-color: #ef4444; }
.cdde-badge { font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; font-weight: 600;
  padding: 0.15rem 0.5rem; border-radius: 4px; text-transform: uppercase; display: inline-block; }
.cdde-badge.pass { background: rgba(62,207,142,0.18); color: #3ecf8e; }
.cdde-badge.warn { background: rgba(240,180,41,0.18); color: #f0b429; }
.cdde-badge.fail { background: rgba(239,68,68,0.18); color: #ef4444; }
.cdde-badge.info { background: rgba(96,165,250,0.18); color: #60a5fa; }
.cdde-overall { background: #1e2025; border-radius: 0.75rem; padding: 1.5rem;
  border: 1px solid #363840; display: flex; align-items: center; gap: 1.5rem; }
.cdde-score { font-family: 'IBM Plex Mono', monospace; font-size: 2.5rem; font-weight: 600; }
.cdde-score.pass { color: #3ecf8e; } .cdde-score.warn { color: #f0b429; }
.cdde-score.fail { color: #ef4444; }
.cdde-code { font-family: 'IBM Plex Mono', monospace; background: #101114;
  border: 1px solid #363840; padding: 0.75rem; border-radius: 0.375rem;
  font-size: 0.75rem; color: #c2c4c9; overflow-x: auto; white-space: pre-wrap; }
</style>
"""


def inject_theme() -> None:
    """Inject AgentLens-inspired dark theme into the Streamlit page."""
    st.markdown(_FONTS + _CSS, unsafe_allow_html=True)


def status_badge(text: str, variant: str = "info") -> str:
    """Return HTML for a styled badge. Variants: 'pass', 'warn', 'fail', 'info'."""
    return f'<span class="cdde-badge {variant}">{text}</span>'


def score_card(label: str, value: str, variant: str = "pass") -> str:
    """Return HTML for a score card with big number + label."""
    return (
        f'<div class="cdde-overall">'
        f'<div><div class="cdde-mono" style="font-size:0.7rem;color:#7d808a;'
        f'text-transform:uppercase">{label}</div>'
        f'<div class="cdde-score {variant}">{value}</div></div></div>'
    )


def result_row(name: str, score: str, message: str, variant: str = "pass") -> str:
    """Return HTML for a result row (name + badge + message)."""
    badge = status_badge(score, variant)
    return (
        f'<div class="cdde-card {variant}">'
        f'<strong style="color:#f0f1f3;font-family:IBM Plex Mono,monospace;'
        f'font-size:0.85rem">{name}</strong> '
        f"{badge}"
        f'<div style="font-size:0.8rem;color:#9a9da5;margin-top:0.25rem">{message}</div>'
        f"</div>"
    )
