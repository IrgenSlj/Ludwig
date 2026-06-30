"""Deterministic params→geometry evaluator (R3 / [H1], DAG-EVAL).

Replays a recorded FeatureGraph (R2) into exact OCCT geometry by dispatching each typed node to the
LOCKED GeometryService primitives — NO LLM, NO exec of generated text. This is the no-compile core:
the same box/hole/translate/compound calls the toolkit makes, driven from the recorded ops instead of
from an LLM-generated CadQuery program. Proving its output matches the closure path (the eval oracle)
is the R3 gate.

No caching (R3): every call re-evaluates the whole graph from its roots. Content-hash caching +
incremental `set_param` (rebuild only the dirty descendants) is R4.

Scope (R3): linear, box-rooted graphs — box + holes/anchors, optional place — carry unambiguous
lineage, so the evaluator reproduces the closure path with full fidelity, and those are gated.
Multi-root composition (stack/assembly) is dispatched too (compound/translate), but the R2 recorder
shares a single FeatureGraph.result_id across the elements of an assembly, so per-child lineage is not
yet recoverable from the graph. `is_graph_expressible` reports those (and raw-CadQuery-closure briefs,
whose geometry the recorder never saw, leaving an empty/rootless graph) as not-yet-expressible, and the
text-substitution fallback stays for them — see docs/REBUILD_ROADMAP.md cross-cutting notes. The fix is
a per-element result id in the recorder, deliberately deferred (grow the IR from real use).
"""
from __future__ import annotations

from ir.elements import BRepHandle
from ir.feature import FeatureGraph
from geometry.service import GeometryService


class EvaluatorError(ValueError):
    """A FeatureGraph node could not be dispatched — unknown op, or a missing/dangling input."""


def evaluate(graph: FeatureGraph, *, geom: GeometryService | None = None) -> BRepHandle:
    """Build the solid a FeatureGraph describes by replaying its nodes onto GeometryService.

    Returns the BRepHandle for ``graph.result_id`` (lazy — the kernel only runs on ``.solid()``).
    Raises EvaluatorError on an unknown op or a dangling input reference.
    """
    g = geom or GeometryService()
    handles: dict[str, BRepHandle] = {}

    def src(node) -> BRepHandle:
        """The handle this op operates on — the last of its recorded inputs (the upstream solid)."""
        if not node.inputs:
            raise EvaluatorError(f"{node.op} {node.node_id!r} has no input solid to operate on")
        prev = node.inputs[-1]
        if prev not in handles:
            raise EvaluatorError(f"{node.node_id!r} references unbuilt input {prev!r}")
        return handles[prev]

    for node in graph.nodes:
        op, p = node.op, node.params
        if op == "box":
            h = g.box(p["length"], p["width"], p["height"])
        elif op == "hole":
            h = g.hole(src(node), p["diameter"], tuple(p["at"]),
                       through=p.get("through", True), depth=p.get("depth"))
        elif op == "anchor":
            h = g.hole(src(node), p["diameter"], tuple(p["at"]), through=False, depth=p["depth"])
        elif op == "place":
            h = g.translate(src(node), tuple(p["offset"]))
        elif op == "stack":
            # stack lifted `top` (the last recorded input) by the stored offset; result is the placed top
            h = g.translate(src(node), tuple(p["offset"]))
        elif op == "assembly":
            missing = [i for i in node.inputs if i not in handles]
            if missing:
                raise EvaluatorError(f"assembly {node.node_id!r} references unbuilt inputs {missing}")
            h = g.compound([handles[i] for i in node.inputs])
        else:
            raise EvaluatorError(f"unknown feature op {op!r}")
        handles[node.node_id] = h

    if graph.result_id not in handles:
        raise EvaluatorError(f"graph result {graph.result_id!r} was never built")
    return handles[graph.result_id]


def is_graph_expressible(graph: FeatureGraph) -> bool:
    """True when ``graph`` is a linear, box-rooted chain the evaluator reproduces with full fidelity.

    A linear chain (box → hole/anchor/place → …, each op on its predecessor) carries unambiguous
    lineage, so evaluate() matches the closure path exactly. Returns False for:
      - an empty graph — the build used a raw-CadQuery closure the recorder never saw (the filleted /
        slotted / chamfered / counterbored / profile briefs);
      - a rootless graph (first op not ``box``) — e.g. a panel + anchors (panel() doesn't record);
      - any graph containing ``stack``/``assembly`` — multi-root lineage isn't recoverable from the R2
        recorder's shared result_id yet.
    Those keep the text-substitution fallback until per-element lineage is first-class.
    """
    nodes = graph.nodes
    if not nodes or nodes[0].op != "box":
        return False
    if any(n.op in ("stack", "assembly") for n in nodes):
        return False
    for i, n in enumerate(nodes[1:], 1):           # each later node operates on exactly its predecessor
        if n.inputs != [nodes[i - 1].node_id]:
            return False
    return True


__all__ = ["evaluate", "is_graph_expressible", "EvaluatorError"]
