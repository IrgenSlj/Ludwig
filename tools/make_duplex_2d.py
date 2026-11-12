"""Write the invented 2D delivery of the Duplex project: a DXF floor plan with joinery blocks.

Usage: python tools/make_duplex_2d.py   (rewrites fixtures/dxf/duplex_joinery_plan.dxf)

The positions, sizes, levels and opening directions come from the Duplex IFC model, so the
2D delivery describes the same project as the IFC version (PLAN phase 3 gate).
"""

from __future__ import annotations

from pathlib import Path

import ezdxf

from ludwig.parsers import ifc

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "fixtures" / "ifc" / "duplex_architectural_ifc2x3.ifc"
OUT = ROOT / "fixtures" / "dxf" / "duplex_joinery_plan.dxf"
DIRECTION = {"left": "L", "right": "R"}


def main() -> None:
    """Rebuild the DXF fixture from the model."""
    elements, _ = ifc.parse(MODEL)
    ezdxf.options.write_fixed_meta_data_for_testing = True  # same bytes on every run
    doc = ezdxf.new("R2018", setup=False)
    doc.header["$INSUNITS"] = 4  # millimetres
    doc.layers.add("KOZIJNEN")
    doc.layers.add("TEKST")
    msp = doc.modelspace()
    x = 0.0
    for el in sorted(elements, key=lambda e: (e.mark, e.location or "", e.id)):
        direction = el.props.get("opening_direction")
        is_door = direction is not None
        name = f"{'DEUR' if is_door else 'KOZ'}-{el.mark}" + (
            f"-{DIRECTION[direction]}" if is_door else "")  # fmt: skip
        if name not in doc.blocks:
            block = doc.blocks.new(name)
            w = el.width_mm
            block.add_lwpolyline([(0, 0), (w, 0), (w, 100), (0, 100)], close=True)
            if is_door:
                hinge = 0 if direction == "left" else w
                block.add_line((hinge, 100), (hinge, 100 + w))
                start, end = (0, 90) if direction == "left" else (90, 180)
                block.add_arc((hinge, 100), w, start, end)
            for i, tag in enumerate(("MERK", "BREEDTE", "HOOGTE", "VERDIEPING", "DRAAIRICHTING")):
                block.add_attdef(tag, (0, -150 - 120 * i), dxfattribs={"height": 100})
        for _ in range(el.quantity):
            ref = msp.add_blockref(name, (x, 0), dxfattribs={"layer": "KOZIJNEN"})
            values = {"MERK": el.mark, "HOOGTE": f"{el.height_mm:g}",
                      "VERDIEPING": el.location or ""}  # fmt: skip
            if not is_door:  # door widths come from the block extents
                values["BREEDTE"] = f"{el.width_mm:g}"
            if is_door:
                values["DRAAIRICHTING"] = "links" if direction == "left" else "rechts"
            ref.add_auto_attribs(values)
            x += el.width_mm + 1000
    msp.add_text("Kozijnen begane grond en verdieping (invented)", dxfattribs={
        "layer": "TEKST", "height": 250, "insert": (0, 2000)})  # fmt: skip
    doc.saveas(OUT)


if __name__ == "__main__":
    main()
