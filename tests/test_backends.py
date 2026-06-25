"""Backend tests — require the OCCT kernel, skipped if absent."""
import pytest

pytest.importorskip("cadquery")

from backends import step
from toolkit import box, clearance_hole


def test_step_exports_and_round_trips(tmp_path):
    el = box("bracket", 80, 40, 6)
    clearance_hole(el, "M8", (-25, 0))
    clearance_hole(el, "M8", (25, 0))

    path = step.compile(el, tmp_path)
    assert path.exists() and path.stat().st_size > 0

    # re-read through OCCT (the kernel FreeCAD/CAD tools use) — proves it's valid, openable geometry
    length, width, height = step.reimport_bbox(path)
    assert abs(length - 80) < 1e-3 and abs(width - 40) < 1e-3 and abs(height - 6) < 1e-3


def test_step_is_a_fabrication_export():
    assert step.fabrication is True  # gated behind the pre-export critic hook (BRIEF §5)
