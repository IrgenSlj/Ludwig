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
from geometry.evaluator import EvaluatorError, evaluate, is_graph_expressible
from ir.feature import FeatureGraph
from toolkit import box, clearance_hole
from toolkit.elements import recording
from toolkit.standards import bbox_gate

# Box-rooted linear chains (box + holes) — unambiguous lineage, fully reproduced by the evaluator.
EXPRESSIBLE = ["bracket", "plate", "spacer", "flat_bar", "gusset", "asymmetric_gusset"]
# Raw-CadQuery closures (fillet/slot/chamfer/cbore), panel+anchors, profile, assembly — fall back.
NOT_EXPRESSIBLE = ["filtered_bracket", "slotted_plate", "chamfered_spacer", "counterbored_plate",
                   "precast_panel", "stacked_plates", "steel_beam"]


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
