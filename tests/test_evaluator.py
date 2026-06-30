"""Evaluator parity tests (R3) — the no-LLM params→geometry compiler matches the closure oracle.

Require the OCCT kernel, skipped if absent. Proves the deterministic evaluator (replaying a recorded
FeatureGraph onto GeometryService) reproduces the reference oracle's geometry for the graph-expressible
briefs, and that raw-closure / multi-root briefs are honestly flagged not-yet-expressible.
"""
import pytest

pytest.importorskip("cadquery")

from eval import reference
from eval.briefs import BRIEFS
from geometry import GeometryService
from geometry.evaluator import (EvaluatorError, Evaluator, descendants, evaluate,
                                is_graph_expressible)
from ir.feature import FeatureGraph
from toolkit import assembly, box, clearance_hole, stack
from toolkit.elements import recording
from toolkit.standards import bbox_gate

# Box-rooted DAGs the evaluator reproduces fully: box+holes chains, and (since the per-element
# lineage fix) stack/assembly composition.
EXPRESSIBLE = ["bracket", "plate", "spacer", "flat_bar", "gusset", "asymmetric_gusset",
               "stacked_plates"]
# Raw-CadQuery closures (fillet/slot/chamfer/cbore), panel+anchors, profile — graph empty/rootless.
NOT_EXPRESSIBLE = ["filtered_bracket", "slotted_plate", "chamfered_spacer", "counterbored_plate",
                   "precast_panel", "steel_beam"]


def _record(bid):
    brief = next(b for b in BRIEFS if b["id"] == bid)
    with recording() as graph:
        el = reference.build(brief)   # ops recorded as a side-effect of the closure build
    return el, graph


@pytest.mark.parametrize("bid", EXPRESSIBLE)
def test_evaluator_matches_oracle(bid):
    el, graph = _record(bid)
    assert is_graph_expressible(graph)
    g = GeometryService()
    ev = evaluate(graph)
    ob, eb = g.bbox(el.geometry), g.bbox(ev)
    tol = bbox_gate()
    assert all(abs(a - b) <= tol for a, b in zip(ob, eb)), (bid, ob, eb)
    assert g.cylindrical_face_count(ev) == g.cylindrical_face_count(el.geometry)
    assert g.is_valid(ev)


@pytest.mark.parametrize("bid", NOT_EXPRESSIBLE)
def test_non_expressible_falls_back(bid):
    _el, graph = _record(bid)
    assert not is_graph_expressible(graph)


def test_evaluator_is_lazy():
    # evaluate() returns a handle that hasn't touched the kernel until .solid() is forced
    with recording() as graph:
        box("b", 80, 40, 6)
    ev = evaluate(graph)
    assert not ev.built
    ev.solid()
    assert ev.built


def test_evaluator_reboots_the_right_hole_count():
    with recording() as graph:
        b = box("b", 80, 40, 6)
        clearance_hole(b, "M8", (-25, 0))
        clearance_hole(b, "M8", (25, 0))
    ev = evaluate(graph)
    assert GeometryService().cylindrical_face_count(ev) == 2


def test_unknown_op_raises():
    g = FeatureGraph()
    g.append("frobnicate", {}, [])
    with pytest.raises(EvaluatorError):
        evaluate(g)


# ---- R4: content-hash cache + incremental set_param (tree-reduction) ----

def test_set_param_rebuilds_only_dirty_descendants_bracket():
    with recording() as g:
        b = box("b", 80, 40, 6)
        clearance_hole(b, "M8", (-25, 0))
        clearance_hole(b, "M8", (25, 0))
    ev = Evaluator(g)
    _, warm = ev.build()
    assert warm == {"box#1", "hole#1", "hole#2"}              # first build is full
    h, rebuilt = ev.set_param("box#1", "length", 100)
    assert rebuilt == descendants(g, "box#1") == {"box#1", "hole#1", "hole#2"}
    assert abs(GeometryService().bbox(h)[0] - 100) < 1e-6     # the edit took effect


def test_set_param_assembly_does_not_rebuild_base():
    with recording() as g:
        base = box("base", 60, 60, 10)
        top = box("top", 40, 40, 10)
        stack(base, top)
        assembly("a", base, top)
    ev = Evaluator(g)
    ev.build()
    h, rebuilt = ev.set_param("box#2", "height", 20)          # resize the top plate
    assert "box#1" not in rebuilt                              # the base is reused from cache
    assert rebuilt == descendants(g, "box#2") == {"box#2", "stack#1", "assembly#1"}
    length, width, _ = GeometryService().bbox(h)
    assert abs(length - 60) < 1e-6 and abs(width - 60) < 1e-6  # base footprint preserved


def test_set_param_to_same_value_rebuilds_nothing():
    with recording() as g:
        box("b", 80, 40, 6)
    ev = Evaluator(g)
    ev.build()
    _, rebuilt = ev.set_param("box#1", "length", 80)          # unchanged → content key stable
    assert rebuilt == set()


def test_cache_reuse_across_independent_edits():
    # two successive edits each rebuild only their own dirty subtree; the cache retains prior handles
    with recording() as g:
        b = box("b", 80, 40, 6)
        clearance_hole(b, "M8", (-25, 0))
    ev = Evaluator(g)
    ev.build()
    _, r1 = ev.set_param("box#1", "width", 50)
    assert r1 == {"box#1", "hole#1"}
    _, r2 = ev.set_param("hole#1", "diameter", 11.0)          # only the hole node is dirty now
    assert r2 == {"hole#1"}
