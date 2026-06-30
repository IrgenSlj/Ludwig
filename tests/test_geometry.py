"""Geometry + pass-rate harness tests — require the OCCT kernel, skipped if absent."""
import pytest

pytest.importorskip("cadquery")

from eval import harness, reference
from eval.briefs import BRIEFS
from geometry import GeometryService
from toolkit import box, clearance_hole
from toolkit.standards import clearance_hole_mm


def test_box_bbox_is_exact():
    length, width, height = GeometryService().bbox(box("b", 80, 40, 6).geometry)
    assert abs(length - 80) < 1e-6 and abs(width - 40) < 1e-6 and abs(height - 6) < 1e-6


def test_clearance_hole_count_and_size():
    el = box("b", 80, 40, 6)
    clearance_hole(el, "M8", (-25, 0))
    clearance_hole(el, "M8", (25, 0))
    assert GeometryService().cylindrical_face_count(el.geometry) == 2
    assert clearance_hole_mm("M8") == 9.0  # standards.yaml, not guessed


def test_reference_oracle_passes_every_brief():
    rate, results = harness.run(reference.build)
    assert rate == 1.0, results


def test_precast_panel_builds_and_passes():
    from eval import reference
    from eval.briefs import BRIEFS
    from eval.harness import geometric_pass
    from geometry import GeometryService
    from toolkit.standards import bbox_gate

    pb = next(b for b in BRIEFS if b["id"] == "precast_panel")
    el = reference.build(pb)
    assert el.type == "Panel"  # the new IR type is exercised
    assert geometric_pass(el, pb, GeometryService(), bbox_gate())  # 3000×200×2000, 2 anchor pockets


def test_stair_is_one_valid_prism_with_correct_extents():
    from toolkit import stair
    el = stair("s", rise=170, going=280, width=1000, riser_count=17)
    assert el.type == "Stair"
    g = GeometryService()
    length, width, height = g.bbox(el.geometry)
    assert abs(length - 17 * 280) < 1e-6 and abs(width - 1000) < 1e-6 and abs(height - 17 * 170) < 1e-6
    assert g.is_valid(el.geometry)
    assert g.cylindrical_face_count(el.geometry) == 0          # saw-tooth prism, no booleans/holes
    assert el.dim("rise") == 170 and el.dim("going") == 280 and el.dim("riser_count") == 17
    assert el.dim("floor_to_floor") == 17 * 170


def test_wall_opening_cuts_a_void_and_hosts_it():
    from toolkit import opening, wall
    g = GeometryService()
    w = wall("w", 3000, 2400, 200)
    vol0 = g.volume(w.geometry)
    op = opening(w, 900, 2100, (0, 0))
    assert op.type == "Opening" and op.dim("width") == 900 and op.dim("height") == 2100
    assert g.is_valid(w.geometry) and g.volume(w.geometry) < vol0          # void removed material
    assert any(r.kind == "hosts" and r.target_id == op.id for r in w.relations)
    length, thickness, height = g.bbox(w.geometry)                          # overall extents unchanged
    assert abs(length - 3000) < 1e-6 and abs(thickness - 200) < 1e-6 and abs(height - 2400) < 1e-6


def test_harness_discriminates_a_wrong_build():
    # an off-by-5mm height build must FAIL the gate — proves the instrument has real signal
    def bad(b):
        d = b["dims"]
        return box(b["id"], d["length"], d["width"], d["height"] + 5)

    rate, _ = harness.run(bad, briefs=[BRIEFS[1]])  # plate (0 holes)
    assert rate == 0.0
