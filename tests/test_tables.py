from pathlib import Path

import ezdxf

from ludwig.parsers import dxf, schedule
from ludwig.parsers.tables import Segment, Text, cell_text, grid

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def ruled(xs, ys):
    return ([Segment(xs[0], y, xs[-1], y) for y in ys]
            + [Segment(x, ys[0], x, ys[-1]) for x in xs])  # fmt: skip


def test_grid_places_text_by_centre_top_row_first():
    texts = [Text(5, 15, "Merk"), Text(15, 15, "Aantal"), Text(5, 5, "K1"), Text(15, 5, "4"),
             Text(16, 4, "st"), Text(50, 50, "outside")]  # fmt: skip
    cells = grid(ruled([0, 10, 20], [0, 10, 20]), texts)
    assert [[cell_text(c) for c in row] for row in cells] == [["Merk", "Aantal"], ["K1", "4 st"]]


def test_grid_with_y_down_and_no_rules():
    cells = grid(ruled([0, 10], [0, 10, 20]), [Text(5, 3, "top"), Text(5, 13, "bottom")],
                 y_up=False)  # fmt: skip
    assert [[cell_text(c) for c in row] for row in cells] == [["top"], ["bottom"]]
    assert grid([Segment(0, 0, 10, 0)], [Text(1, 1, "x")]) == []


def summary(elements):
    return sorted((e.mark, e.quantity, e.width_mm, e.height_mm, e.location,
                   tuple(sorted(e.props.items()))) for e in elements)  # fmt: skip


def test_schedule_drawn_in_dxf_reads_like_the_csv():
    drawn = FIX / "dxf" / "duplex_joinery_schedule.dxf"
    mapping = dxf.load_mapping(drawn.with_suffix(".mapping.yaml"))
    elements, warnings = dxf.parse(drawn, mapping)
    assert warnings == []
    csv = FIX / "schedule" / "duplex_joinery_schedule.csv"
    expected, _ = schedule.parse(csv, schedule.load_mapping(csv.with_suffix(".mapping.yaml")))
    assert summary(elements) == summary(expected)
    width = elements[0].field_sources["width_mm"]
    assert (width.kind.value, width.layer, width.cell) == ("dxf", "STAAT", "D2")
    assert width.dxf_handle


def test_missing_table_is_a_warning(tmp_path):
    doc = ezdxf.new(setup=False)
    doc.modelspace().add_text("loose", dxfattribs={"layer": "STAAT"})
    path = tmp_path / "t.dxf"
    doc.saveas(path)
    mapping = {"blocks": {}, "tables": [{"layers": ["STAAT"], "type": "frame",
                                         "columns": {"mark": "Merk"}}]}  # fmt: skip
    assert dxf.parse(path, mapping) == ([], [dxf.ParseWarning(
        str(path), "table 1: no ruled table on layers ['STAAT']")])  # fmt: skip
