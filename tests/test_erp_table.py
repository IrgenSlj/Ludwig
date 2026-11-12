from collections import Counter
from pathlib import Path

from ludwig.adapters import erp_table
from ludwig.model import ElementType, Side, SourceKind

ERP = Path(__file__).resolve().parent.parent / "fixtures" / "erp"
EXPORT = ERP / "duplex_erp_export.csv"


def parse(path=EXPORT):
    return erp_table.parse(path, erp_table.load_mapping(ERP / "duplex_erp_export.mapping.yaml"))


def test_sample_export_parses_to_erp_frames():
    elements, warnings = parse()
    assert warnings == []
    assert len(elements) == 12  # the Montage line is skipped
    assert {e.side for e in elements} == {Side.ERP}
    assert {e.type for e in elements} == {ElementType.FRAME}
    assert {s.kind for e in elements for s in e.sources} == {SourceKind.ERP}
    per_mark = Counter()
    for e in elements:
        per_mark[e.mark] += e.quantity
    assert per_mark == {"01": 4, "02": 8, "03": 4, "04": 4, "05": 2, "28": 4, "32": 6,
                        "33": 2, "36": 2, "56": 2}  # fmt: skip
    roof = next(e for e in elements if e.mark == "36")
    assert (roof.width_mm, roof.height_mm) == (1172.5, 634.8)
    door = next(e for e in elements if e.mark == "33")
    assert door.props == {"fire_rating_min": 30.0, "opening_direction": "rechts"}
    assert door.source_of("props.fire_rating_min").cell == "J11"


def test_unreadable_export_is_a_warning(tmp_path):
    bad = tmp_path / "export.xlsx"
    bad.write_text("not a workbook")
    elements, warnings = parse(bad)
    assert elements == [] and "cannot read" in warnings[0].message
