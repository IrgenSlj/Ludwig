"""Deterministic params→geometry evaluator + incremental cache (R3/R4 / [H1], DAG-EVAL).

Replays a recorded FeatureGraph (R2) into exact OCCT geometry by dispatching each typed node to the
LOCKED GeometryService primitives — NO LLM, NO exec of generated text. This is the no-compile core:
the same box/hole/translate/compound calls the toolkit makes, driven from the recorded ops instead of
from an LLM-generated CadQuery program. Proving its output matches the closure path (the eval oracle)
is the R3 gate.

R3: `evaluate(graph)` — a full re-eval, no caching.
R4: `Evaluator` — a content-hash cache + `set_param`, so editing one parameter recomputes only the
    dirty descendant subtree and reuses every clean subtree from cache (tree-reduction).

Expressibility: a graph is graph-expressible when it is box-rooted and every node's inputs reference
earlier nodes (a valid DAG over the known ops) — true for the box+holes/anchors briefs AND, since the
per-element lineage fix (R4), for stack/assembly composition. A build that used a raw-CadQuery closure
the recorder never saw yields an empty or rootless graph and stays on the text-substitution fallback
(the filleted/slotted/chamfered/counterbored briefs; panel+anchors; profile). The selftest parity check
is the backstop: any expressible graph whose evaluation diverges from the oracle turns the gate red.
"""
from __future__ import annotations

import hashlib

from ir.elements import BRepHandle
from ir.feature import FeatureGraph
from geometry.service import GeometryService

_KNOWN_OPS = {"box", "hole", "anchor", "place", "stack", "assembly"}


class EvaluatorError(ValueError):
    """A FeatureGraph node could not be dispatched — unknown op, or a missing/dangling input."""


def _apply(g: GeometryService, op: str, params: dict, inputs: list[BRepHandle]) -> BRepHandle:
    """Dispatch one node to the locked GeometryService primitives. `inputs` are the resolved
    handles for the node's recorded inputs (the upstream solids), in order."""
    if op == "box":
        return g.box(params["length"], params["width"], params["height"])
    if op == "assembly":
        if not inputs:
            raise EvaluatorError("assembly has no children to compound")
        return g.compound(inputs)
    if not inputs:                                  # the remaining ops modify a single upstream solid
        raise EvaluatorError(f"{op} has no input solid to operate on")
    src = inputs[-1]
    if op == "hole":
        return g.hole(src, params["diameter"], tuple(params["at"]),
                      through=params.get("through", True), depth=params.get("depth"))
    if op == "anchor":
        return g.hole(src, params["diameter"], tuple(params["at"]), through=False, depth=params["depth"])
    if op in ("place", "stack"):                    # stack lifted `top` (last input) by the stored offset
        return g.translate(src, tuple(params["offset"]))
    raise EvaluatorError(f"unknown feature op {op!r}")


def evaluate(graph: FeatureGraph, *, geom: GeometryService | None = None) -> BRepHandle:
    """Build the solid a FeatureGraph describes by replaying its nodes onto GeometryService (R3).

    Full re-eval, no caching. Returns the lazy BRepHandle for ``graph.result_id`` (the kernel only
    runs on ``.solid()``). Raises EvaluatorError on an unknown op or a dangling input reference.
    """
    g = geom or GeometryService()
    handles: dict[str, BRepHandle] = {}
    for node in graph.nodes:
        missing = [i for i in node.inputs if i not in handles]
        if missing:
            raise EvaluatorError(f"{node.node_id!r} references unbuilt input(s) {missing}")
        handles[node.node_id] = _apply(g, node.op, node.params, [handles[i] for i in node.inputs])
    if graph.result_id not in handles:
        raise EvaluatorError(f"graph result {graph.result_id!r} was never built")
    return handles[graph.result_id]


def is_graph_expressible(graph: FeatureGraph) -> bool:
    """True when the evaluator reproduces the closure path for ``graph`` with full fidelity.

    Requires: non-empty, box-rooted (first op ``box``), every op known, every input referencing an
    earlier node (a valid topological DAG), and a result that was built. This admits linear chains
    (box + holes/anchors) and — since the per-element lineage fix — stack/assembly composition.
    Returns False for an empty graph (raw-CadQuery closure not recorded) or a rootless one (panel +
    anchors / profile), which stay on the text-substitution fallback.
    """
    nodes = graph.nodes
    if not nodes or nodes[0].op != "box":
        return False
    seen: set[str] = set()
    for n in nodes:
        if n.op not in _KNOWN_OPS:
            return False
        if any(i not in seen for i in n.inputs):     # inputs must be earlier nodes — no cycles/dangling
            return False
        seen.add(n.node_id)
    return graph.result_id in seen


def descendants(graph: FeatureGraph, node_id: str) -> set[str]:
    """`node_id` plus every node that transitively depends on it — the dirty set a param edit forces
    a rebuild of. Single forward pass works because nodes are in construction (topological) order."""
    dirty = {node_id}
    for n in graph.nodes:
        if any(i in dirty for i in n.inputs):
            dirty.add(n.node_id)
    return dirty


def _canon(v, tol: float):
    """Canonicalize a param value for content-hashing: quantize floats to the tol grid (so float
    noise below tol doesn't bust the cache) and normalize containers/dicts to ordered tuples."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return round(v / tol) * tol if tol else v
    if isinstance(v, (list, tuple)):
        return tuple(_canon(x, tol) for x in v)
    if isinstance(v, dict):
        return tuple(sorted((k, _canon(x, tol)) for k, x in v.items()))
    return v


def _node_key(op: str, params: dict, input_keys: list[str], tol: float) -> str:
    """Content key for a node: a hash of (op, quantized params, upstream content keys). Because the
    input keys roll up the whole upstream subtree, two nodes with identical construction history get
    identical keys — and a key changes iff this node or any ancestor changed."""
    payload = (op, _canon(params, tol), tuple(input_keys))
    return hashlib.sha1(repr(payload).encode()).hexdigest()


class EvalCache:
    """Content-key → built BRepHandle. Unchanged subtrees are reused across evaluations by key."""

    def __init__(self) -> None:
        self._by_key: dict[str, BRepHandle] = {}

    def get(self, key: str):
        return self._by_key.get(key)

    def put(self, key: str, handle: BRepHandle) -> None:
        self._by_key[key] = handle

    def __len__(self) -> int:
        return len(self._by_key)


class Evaluator:
    """Incremental evaluator over a FeatureGraph (R4): a content-hash cache + ``set_param``.

    ``build()`` evaluates the graph (applying any accumulated param overrides), reusing every node
    whose content key is unchanged and rebuilding only the rest; it returns ``(handle, rebuilt_ids)``.
    ``set_param`` records an override and rebuilds — after the first (warm) build, only the changed
    node's dirty descendant subtree is rebuilt; clean subtrees (e.g. an assembly's untouched base) are
    served from cache. ``rebuilt_ids`` is therefore exactly ``descendants(node_id)`` for a single edit.
    """

    def __init__(self, graph: FeatureGraph, *, geom: GeometryService | None = None,
                 tol: float = 1e-6, cache: EvalCache | None = None) -> None:
        self.graph = graph
        self.geom = geom or GeometryService()
        self.tol = tol
        self.cache = cache if cache is not None else EvalCache()   # share across drag ticks (R7)
        self._overrides: dict[str, dict] = {}

    def build(self) -> tuple[BRepHandle, set[str]]:
        """Evaluate the graph under current overrides. Returns (result handle, set of node_ids that
        were rebuilt this call — i.e. cache misses). The first build rebuilds everything."""
        handles: dict[str, BRepHandle] = {}
        keys: dict[str, str] = {}
        rebuilt: set[str] = set()
        for node in self.graph.nodes:
            missing = [i for i in node.inputs if i not in keys]
            if missing:
                raise EvaluatorError(f"{node.node_id!r} references unbuilt input(s) {missing}")
            eff = node.params if node.node_id not in self._overrides \
                else {**node.params, **self._overrides[node.node_id]}
            key = _node_key(node.op, eff, [keys[i] for i in node.inputs], self.tol)
            cached = self.cache.get(key)
            if cached is not None:
                handles[node.node_id] = cached
            else:
                h = _apply(self.geom, node.op, eff, [handles[i] for i in node.inputs])
                self.cache.put(key, h)
                handles[node.node_id] = h
                rebuilt.add(node.node_id)
            keys[node.node_id] = key
        if self.graph.result_id not in handles:
            raise EvaluatorError(f"graph result {self.graph.result_id!r} was never built")
        return handles[self.graph.result_id], rebuilt

    def set_param(self, node_id: str, name: str, value) -> tuple[BRepHandle, set[str]]:
        """Override one node's parameter and rebuild only the dirty descendants. Returns
        (result handle, rebuilt node_ids). Setting a param to its current value rebuilds nothing."""
        self._overrides.setdefault(node_id, {})[name] = value
        return self.build()


__all__ = ["evaluate", "is_graph_expressible", "descendants", "EvalCache", "Evaluator",
           "EvaluatorError"]
