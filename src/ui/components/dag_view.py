"""DAG visualization component with AgentLens color scheme."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.models import DerivationStatus

if TYPE_CHECKING:
    from src.domain.dag import DerivationDAG

_STATUS_COLORS: dict[DerivationStatus, str] = {
    DerivationStatus.APPROVED: "#3ecf8e",
    DerivationStatus.QC_MISMATCH: "#ef4444",
    DerivationStatus.QC_PASS: "#60a5fa",
    DerivationStatus.IN_PROGRESS: "#f0b429",
    DerivationStatus.PENDING: "#7d808a",
    DerivationStatus.FAILED: "#ef4444",
}


def render_dag_dot(dag: DerivationDAG) -> str:
    """Convert DAG to Graphviz DOT format with AgentLens dark theme."""
    lines = [
        "digraph G {",
        "  rankdir=LR;",
        '  bgcolor="#101114";',
        '  node [fontname="IBM Plex Mono" fontcolor="#f0f1f3" fontsize=10 style=filled shape=box];',
        '  edge [color="#363840" arrowsize=0.7];',
    ]
    for var, node in dag.nodes.items():
        color = _STATUS_COLORS.get(node.status, "#7d808a")
        lines.append(f'  "{var}" [fillcolor="{color}"];')
    for var, node in dag.nodes.items():
        for src in node.rule.source_columns:
            if src in dag.nodes:
                lines.append(f'  "{src}" -> "{var}";')
    lines.append("}")
    return "\n".join(lines)
