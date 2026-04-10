"""DAG engine — build dependency graph from derivation rules, compute topological layers."""

from __future__ import annotations

import networkx as nx

from src.domain.exceptions import DAGError
from src.domain.models import DAGNode, DerivationRule, DerivationRunResult


class DerivationDAG:
    """Dependency graph for derivation rules."""

    def __init__(self, rules: list[DerivationRule], source_columns: set[str]) -> None:
        """Build DAG from rules. source_columns are columns available in the source data."""
        self._graph: nx.DiGraph[str] = nx.DiGraph()
        self._nodes: dict[str, DAGNode] = {}
        self._layers: list[list[str]] | None = None

        derived_names = {r.variable for r in rules}

        for rule in rules:
            self._graph.add_node(rule.variable)
            self._nodes[rule.variable] = DAGNode(rule=rule)

        for rule in rules:
            for col in rule.source_columns:
                if col in derived_names:
                    self._graph.add_edge(col, rule.variable)
                elif col not in source_columns:
                    msg = f"Unknown source column: {col}"
                    raise ValueError(msg)

        if not nx.is_directed_acyclic_graph(self._graph):
            cycle: list[tuple[str, str]] = nx.find_cycle(self._graph)  # type: ignore[assignment]
            msg = f"Circular dependency detected: {cycle}"
            raise ValueError(msg)

        self._compute_layers()

    def _compute_layers(self) -> None:
        """Compute topological layers and assign layer index to each node."""
        self._layers = [
            list(gen)
            for gen in nx.topological_generations(self._graph)  # type: ignore[arg-type]
        ]
        for layer_idx, variables in enumerate(self._layers):
            for var in variables:
                self._nodes[var].layer = layer_idx

    @property
    def nodes(self) -> dict[str, DAGNode]:
        """Variable name -> DAGNode mapping."""
        return dict(self._nodes)

    @property
    def layers(self) -> list[list[str]]:
        """Topological layers — variables in same layer have no mutual dependencies."""
        if self._layers is None:
            self._compute_layers()
        if self._layers is None:
            raise DAGError("Failed to compute topological layers")
        return list(self._layers)

    @property
    def execution_order(self) -> list[str]:
        """Flat topological order of variable names."""
        return [var for layer in self.layers for var in layer]

    def get_node(self, variable: str) -> DAGNode:
        """Get node by variable name. Raises KeyError if not found."""
        return self._nodes[variable]

    def get_dependencies(self, variable: str) -> list[str]:
        """Return variables that this variable depends on."""
        return list(self._graph.predecessors(variable))

    def apply_run_result(self, result: DerivationRunResult) -> None:
        """Atomically update a DAG node from a derivation run result."""
        node = self._nodes[result.variable]
        node.status = result.status
        for field in (
            "coder_code",
            "coder_approach",
            "qc_code",
            "qc_approach",
            "qc_verdict",
            "approved_code",
            "debug_analysis",
        ):
            value = getattr(result, field)
            if value is not None:
                setattr(node, field, value)
