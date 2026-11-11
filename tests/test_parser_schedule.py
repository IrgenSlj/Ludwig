import csv
from pathlib import Path

import openpyxl
import pytest

from ludwig.model import Side, SourceKind
from ludwig.parsers import schedule
from ludwig.parsers.values import as_int, as_number

SCHED = Path(__file__).resolve().parent.parent / "fixtures" / "schedule"
CSV = SCHED / "duplex_joinery_schedule.csv"
MAPPING = schedule.load_mapping(SCHED / "duplex_joinery_schedule.mapping.yaml")


def _to_xlsx(csv_path: Path, out: Path, sheet: str = "Kozijnstaat") -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.reader(f, delimiter=";"):
            ws.append([as_number(v) if v and v[0].isdigit() and k in (2, 3, 4) else v
                       for k, v in enumerate(row)])  # fmt: skip
    wb.save(out)
    return out


def test_invented_csv_schedule_parses():
    elements, warnings = schedule.parse(CSV, MAPPING)
    assert warnings == []
    assert len(elements) == 12
    assert sum(e.quantity for e in elements) == 38  # the Duplex model's 24 windows + 14 doors
    roof = next(e for e in elements if e.mark == "36")
    assert (roof.width_mm, roof.height_mm) == (1172.5, 634.8)  # decimal comma
    door = next(e for e in elements if e.mark == "33")
    assert door.props == {"opening_direction": "rechts", "fire_rating_min": 30.0}
    assert door.field_sources["width_mm"].cell == "D11"
    assert door.sources[0].kind is SourceKind.SHEET and door.sources[0].cell == "A11"
    assert "glazing_type" not in door.props  # "-" is empty


def test_xlsx_gives_the_same_elements_as_csv(tmp_path):
    from_csv, _ = schedule.parse(CSV, MAPPING)
    from_xlsx, warnings = schedule.parse(_to_xlsx(CSV, tmp_path / "s.xlsx"), MAPPING)
    assert warnings == []

    def key(e):
        return (e.mark, e.quantity, e.width_mm, e.height_mm, e.location, e.props)

    assert [key(e) for e in from_xlsx] == [key(e) for e in from_csv]
    assert from_xlsx[0].sources[0].sheet == "Kozijnstaat"


def test_missing_column_gives_a_parse_warning():
    mapping = dict(MAPPING, columns=dict(MAPPING["columns"], depth_mm="Diepte"))
    elements, warnings = schedule.parse(CSV, mapping)
    assert len(elements) == 12
    assert [w.message for w in warnings] == ["column 'Diepte' (depth_mm) not found in row 1"]
    assert all(e.depth_mm is None for e in elements)


def test_unreadable_values_become_none_with_a_warning(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Merk;Aantal;Breedte;Hoogte\nK1;twee;1200;abc\n\nK2;1.5;900;2100\n")
    elements, warnings = schedule.parse(bad, MAPPING)
    k1, k2 = elements
    assert k1.quantity is None and k1.height_mm is None and k1.width_mm == 1200.0
    assert k2.quantity is None
    cells = sorted(w.source.cell for w in warnings if w.source)
    assert cells == ["B2", "B4", "D2"]


def test_units_are_converted_at_the_boundary(tmp_path):
    f = tmp_path / "cm.csv"
    f.write_text("Merk,Breedte\nK1,120.5\n")
    mapping = schedule.load_mapping_dict(
        {"type": "frame", "units": "cm", "columns": {"mark": "Merk", "width_mm": "Breedte"}}
    )
    (el,), _ = schedule.parse(f, mapping)
    assert el.width_mm == 1205.0 and el.quantity == 1


def test_erp_side_uses_erp_source_kind(tmp_path):
    elements, _ = schedule.parse(CSV, MAPPING, side=Side.ERP)
    assert all(e.side is Side.ERP and e.sources[0].kind is SourceKind.ERP for e in elements)


def test_public_cobie_schedule_parses():
    mapping = schedule.load_mapping(SCHED / "duplex_design_cobie.mapping.yaml")
    elements, warnings = schedule.parse(SCHED / "duplex_design_cobie.xlsx", mapping)
    assert warnings == []
    assert sorted(e.mark for e in elements) == [
        "DOORTYPEA", "DOORTYPEB", "DOORTYPEC", "DOORTYPED", "SKYLIGHT",
        "WINDOWTYPEA", "WINDOWTYPEB", "WINDOWTYPEC", "WINDOWTYPED",
    ]  # fmt: skip
    assert all(e.width_mm is None for e in elements)  # COBie 0 means unknown, never 0 mm


def test_unreadable_file_gives_a_warning(tmp_path):
    elements, warnings = schedule.parse(tmp_path / "missing.xlsx", MAPPING)
    assert elements == [] and "cannot read schedule" in warnings[0].message


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "frame", "colums": {}},
        {"type": "door"},
        {"type": "frame", "columns": {"widht_mm": "B"}},
        {"type": "frame", "units": "inch"},
        {"columns": {}},
    ],
)
def test_bad_mapping_is_rejected(bad):
    with pytest.raises(ValueError):
        schedule.load_mapping_dict(bad)


@pytest.mark.parametrize(
    ("raw", "number"),
    [("1200", 1200.0), ("1.200,5", 1200.5), ("1200,5", 1200.5), ("EI 30", 30.0),
     (12, 12.0), ("abc", None), (True, None), (None, None)],
)  # fmt: skip
def test_as_number(raw, number):
    assert as_number(raw) == number


def test_as_int():
    assert as_int("4") == 4 and as_int(4.0) == 4
    assert as_int("1.5") is None and as_int("-1") is None
