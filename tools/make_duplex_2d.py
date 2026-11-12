"""Write the invented 2D delivery of the Duplex project: a DXF floor plan with joinery blocks.

Usage: python tools/make_duplex_2d.py   (rewrites the invented files in fixtures/dxf/, pdf/)

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
SCHEDULE = ROOT / "fixtures" / "schedule" / "duplex_joinery_schedule.csv"
SCHEDULE_DXF = ROOT / "fixtures" / "dxf" / "duplex_joinery_schedule.dxf"
SCHEDULE_PDF = ROOT / "fixtures" / "pdf" / "duplex_joinery_schedule.pdf"
COLUMN_WIDTHS = [600, 2600, 700, 900, 900, 1100, 1300, 1500, 700]
ROW_HEIGHT = 300
DIRECTION = {"left": "L", "right": "R"}


def schedule_dxf() -> None:
    """The invented joinery schedule drawn as a ruled table of lines and text."""
    import csv

    rows = list(csv.reader(SCHEDULE.read_text(encoding="utf-8").splitlines(), delimiter=";"))
    doc = ezdxf.new("R2018", setup=False)
    doc.header["$INSUNITS"] = 4
    doc.layers.add("STAAT")
    msp = doc.modelspace()
    xs = [0]
    for w in COLUMN_WIDTHS:
        xs.append(xs[-1] + w)
    top = len(rows) * ROW_HEIGHT
    for i in range(len(rows) + 1):
        msp.add_line((0, top - i * ROW_HEIGHT), (xs[-1], top - i * ROW_HEIGHT),
                     dxfattribs={"layer": "STAAT"})  # fmt: skip
    for x in xs:
        msp.add_line((x, 0), (x, top), dxfattribs={"layer": "STAAT"})
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if value:
                y = top - r * ROW_HEIGHT - 200
                at = {"layer": "STAAT", "insert": (xs[c] + 50, y)}
                msp.add_text(value, height=100, dxfattribs=at)
    msp.add_text("KOZIJNSTAAT", height=200, dxfattribs={"layer": "STAAT", "insert": (0, top + 200)})
    doc.saveas(SCHEDULE_DXF)


def schedule_pdf() -> None:
    """The invented schedule as a vector PDF over two pages, the header repeated on each."""
    import csv

    import minipdf

    rows = list(csv.reader(SCHEDULE.read_text(encoding="utf-8").splitlines(), delimiter=";"))
    header, body = rows[0], rows[1:]
    widths = [w * 0.07 for w in COLUMN_WIDTHS]  # points
    pages = []
    for chunk in (body[:7], body[7:]):
        page = minipdf.Page()
        page.text(40, 555, "Kozijnstaat Duplex (invented)", size=12)
        table = [header, *chunk]
        xs = [40.0]
        for w in widths:
            xs.append(xs[-1] + w)
        top, height = 530.0, 18.0
        for i in range(len(table) + 1):
            page.line(xs[0], top - i * height, xs[-1], top - i * height)
        for x in xs:
            page.line(x, top, x, top - len(table) * height)
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                if value:
                    page.text(xs[c] + 3, top - (r + 1) * height + 5, value)
        pages.append(page)
    minipdf.write(SCHEDULE_PDF, pages)


def main() -> None:
    """Rebuild the 2D fixtures from the model and the invented schedule."""
    ezdxf.options.write_fixed_meta_data_for_testing = True  # same bytes on every run
    schedule_dxf()
    schedule_pdf()
    elements, _ = ifc.parse(MODEL)
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
