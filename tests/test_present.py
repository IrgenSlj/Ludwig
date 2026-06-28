"""Presentation backend tests — require the OCCT kernel, skipped if absent."""
import pytest

pytest.importorskip("cadquery")

from backends import present
from toolkit import box, clearance_hole


def test_present_assembles_one_page_sheet(tmp_path):
    el = box("bracket", 80, 40, 6)
    clearance_hole(el, "M8", (-25, 0))
    clearance_hole(el, "M8", (25, 0))

    path = present.compile(el, tmp_path)
    assert path.exists() and path.suffix == ".html"
    assert path.name == f"{el.id}.present.html"

    text = path.read_text(encoding="utf-8")
    # the part identity is on the sheet
    assert el.id in text
    # the named-dimension schedule carries the registered dims (name + value)
    assert "length" in text and "80" in text
    # the LUDWIG mark is present (art direction / title block)
    assert "LUDWIG" in text


def test_present_is_not_a_fabrication_export():
    assert present.fabrication is False  # a presentation is a derived view, never gated
