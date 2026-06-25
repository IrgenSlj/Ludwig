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


def test_drawing_exports_svg_with_dims(tmp_path):
    from backends import drawing

    el = box("bracket", 80, 40, 6)
    el.register_dim("note", 0)  # manifest has at least the three extents already
    path = drawing.compile(el, tmp_path)
    assert path.exists() and path.suffix == ".svg"
    text = path.read_text()
    assert "<svg" in text and "length = 80" in text  # HLR projection + dimension overlay
    assert not drawing.fabrication  # a drawing is not a gated fabrication export
