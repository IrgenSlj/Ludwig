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


def test_harness_discriminates_a_wrong_build():
    # an off-by-5mm height build must FAIL the gate — proves the instrument has real signal
    def bad(b):
        d = b["dims"]
        return box(b["id"], d["length"], d["width"], d["height"] + 5)

    rate, _ = harness.run(bad, briefs=[BRIEFS[1]])  # plate (0 holes)
    assert rate == 0.0
