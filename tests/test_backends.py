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


def test_ifc_exports_and_round_trips(tmp_path):
    pytest.importorskip("ifcopenshell")
    from backends import ifc
    from toolkit import anchor, panel

    el = panel("wallpanel", 3000, 2000, 200)
    anchor(el, 17.5, (-750, 0), 150)
    anchor(el, 17.5, (750, 0), 150)
    path = ifc.compile(el, tmp_path)
    assert path.exists() and path.suffix == ".ifc"

    summary = ifc.reimport_summary(path)
    assert summary["schema"] == "IFC4"
    assert summary["element_classes"] == ["IfcWall"]  # Panel -> IfcWall via standards.yaml ifc_map
    # IFC4precast property sets
    assert "PrecastConcrete" in summary["materials"]
    assert "Pset_PrecastConcrete" in summary["property_sets"]


def test_assembly_composes_and_exports_all_backends(tmp_path):
    pytest.importorskip("ifcopenshell")
    from toolkit import assembly, box
    from backends import step, ifc, drawing
    a = box("plate_a", 100, 60, 8)
    b = box("plate_b", 100, 60, 8)
    asm = assembly("lap_joint", a, b, name="Lap joint")
    assert asm.type == "Assembly" and len(asm.children) == 2
    # compound geometry exports through every backend
    sp = step.compile(asm, tmp_path); assert sp.exists() and sp.stat().st_size > 0
    dp = drawing.compile(asm, tmp_path); assert dp.exists() and dp.suffix == ".svg"
    ip = ifc.compile(asm, tmp_path)
    summary = ifc.reimport_summary(ip)
    assert summary["schema"] == "IFC4"
    # the assembly decomposes into its two children (IfcElementAssembly + IfcRelAggregates)
    assert "IfcElementAssembly" in summary["element_classes"]
    assert summary["element_classes"].count("IfcBuildingElementProxy") == 2
    assert summary["assembly_children"] == 2


def test_drawing_exports_svg_with_dims(tmp_path):
    from backends import drawing

    el = box("bracket", 80, 40, 6)
    el.register_dim("note", 0)  # manifest has at least the three extents already
    path = drawing.compile(el, tmp_path)
    assert path.exists() and path.suffix == ".svg"
    text = path.read_text()
    assert "<svg" in text and "length = 80" in text  # HLR projection + dimension overlay
    assert not drawing.fabrication  # a drawing is not a gated fabrication export


# --------------------------------------------------------------------------- #
# the conventioned shop-drawing engine (the moat)
# --------------------------------------------------------------------------- #

def _open_dxf(path):
    ezdxf = pytest.importorskip("ezdxf")
    return ezdxf.readfile(str(path))


def test_hole_records_position_as_a_feature():
    """The IR keeps the hole POSITION (design intent), not just the diameter — what the drawing
    engine and a future 'move the hole' edit both need (grow the IR from real use, principle #7)."""
    el = box("bracket", 80, 40, 6)
    clearance_hole(el, "M8", (-25, 0))
    clearance_hole(el, "M8", (25, 0))
    holes = [f for f in el.features if f.get("kind") == "hole"]
    assert len(holes) == 2
    assert {h["at"] for h in holes} == {(-25.0, 0.0), (25.0, 0.0)}
    assert all(h["diameter"] == 9.0 and h["through"] and h["thread"] == "M8" for h in holes)


def test_shop_drawing_is_a_conventioned_multiview_dxf(tmp_path):
    pytest.importorskip("ezdxf")
    from backends import shopdrawing

    el = box("bracket", 80, 40, 6)
    clearance_hole(el, "M8", (-25, 0))
    clearance_hole(el, "M8", (25, 0))
    path = shopdrawing.compile(el, tmp_path)
    assert path.exists() and path.suffix == ".dxf"
    assert not shopdrawing.fabrication  # a drawing is derived, never a gated fabrication file

    doc = _open_dxf(path)
    msp = doc.modelspace()
    layers = {e.dxf.layer for e in msp}
    # the conventioned layer hierarchy is present (visible / hidden / centre-line / dimension)
    assert {"VISIBLE", "HIDDEN", "CENTRE", "DIMENSION", "BORDER"} <= layers
    # two holes appear as real circles in the plan + a centre cross each
    assert len(msp.query("CIRCLE")) == 2
    # hidden walls (4 per through hole: 2 walls × 2 elevations) and dimensions exist
    assert len(msp.query("LINE[layer=='HIDDEN']")) == 8
    assert len(msp.query("DIMENSION")) >= 3


def test_shop_drawing_dimensions_read_true_mm_via_dimlfac(tmp_path):
    """A 2:1 / 1:20 sheet draws geometry at paper scale but DIMLFAC restores TRUE millimetres —
    the professional mechanism, so a fabricator reads real sizes regardless of plot scale."""
    pytest.importorskip("ezdxf")
    from backends import shopdrawing

    el = box("bracket", 80, 40, 6)
    clearance_hole(el, "M8", (-25, 0))
    clearance_hole(el, "M8", (25, 0))
    doc = _open_dxf(shopdrawing.compile(el, tmp_path))
    dimlfac = doc.dimstyles.get("LUDWIG").dxf.dimlfac
    true_vals = {round(d.get_measurement() * dimlfac) for d in doc.modelspace().query("DIMENSION")}
    assert {80, 40, 6} <= true_vals               # overall length / width / height, exact
    assert {15, 65} <= true_vals                  # both hole x-positions from the left datum


def test_shop_drawing_scale_label():
    from backends import shopdrawing
    assert shopdrawing._scale_label(1) == "1:1"
    assert shopdrawing._scale_label(20) == "1:20"
    assert shopdrawing._scale_label(0.5) == "2:1"     # enlargement for a small part


def test_shop_drawing_blind_anchor_callout(tmp_path):
    pytest.importorskip("ezdxf")
    from backends import shopdrawing
    from toolkit import anchor, panel

    el = panel("wallpanel", 3000, 2000, 200)
    anchor(el, 17.5, (-750, 0), 150)
    anchor(el, 17.5, (750, 0), 150)
    doc = _open_dxf(shopdrawing.compile(el, tmp_path))
    notes = " ".join(t.dxf.text for t in doc.modelspace().query("TEXT"))
    assert "CAST-IN ANCHOR" in notes
    assert "2×" in notes and "17.5" in notes      # grouped callout, ⌀ from the feature
