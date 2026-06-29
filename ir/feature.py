"""Feature graph — records toolkit construction calls as typed nodes (R2 / [H1]).

Pure Python; NO heavy dependencies (no cadquery, no OCCT). The recorder in
toolkit/elements.py appends FeatureNodes as a side-effect of toolkit calls while a
``recording()`` context is active; by default recording is OFF and the existing
closure/geometry path is completely untouched.

All distance/dimension values are in mm (system-wide convention, BRIEF §10).
Node ids are per-op-type counters within a graph: "box#1", "hole#1", "hole#2".
These ids are lineage-stable: identical ops in identical order produce identical ids
across independent builds (deterministic by construction, not by hashing).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FeatureNode:
    """A single recorded toolkit call.

    node_id  — lineage-stable id ("box#1", "hole#2", …); reproducible across runs.
    op       — toolkit operation name ("box", "hole", "anchor", "place", "stack", "assembly").
    params   — op keyword arguments; all distance values are in mm.
    inputs   — node_ids of upstream nodes this op depended on (empty for root constructors).
    """
    node_id: str
    op: str
    params: dict[str, Any]
    inputs: list[str] = field(default_factory=list)


@dataclass
class FeatureGraph:
    """Ordered construction history of an Element, recorded as FeatureNodes.

    nodes      — all nodes in construction order.
    result_id  — node_id of the final result (updated after each append).
    """
    nodes: list[FeatureNode] = field(default_factory=list)
    result_id: str = ""

    def _next_id(self, op: str) -> str:
        """Lineage-stable id for the next node of *op* type: 'box#1', 'hole#2', ..."""
        count = sum(1 for n in self.nodes if n.op == op) + 1
        return f"{op}#{count}"

    def append(self, op: str, params: dict[str, Any], inputs: list[str]) -> FeatureNode:
        """Create and append a FeatureNode with a stable id; update result_id."""
        node = FeatureNode(node_id=self._next_id(op), op=op, params=params, inputs=inputs)
        self.nodes.append(node)
        self.result_id = node.node_id
        return node
