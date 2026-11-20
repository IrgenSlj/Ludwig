"""PLAN 5.7: the mapping builder proposes what a person would have written by hand."""

from pathlib import Path

from ludwig.adapters import erp_table
from ludwig.model import Side
from ludwig.parsers import columns, schedule

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def elements(path, mapping, side):
    found, warnings = schedule.parse(path, mapping, side=side)
    return sorted((e.mark, e.type, e.quantity, e.width_mm, e.height_mm, e.location,
                   sorted(e.props.items())) for e in found), warnings  # fmt: skip


def test_schedule_proposal_reads_the_same_as_the_hand_mapping():
    path = FIX / "schedule" / "duplex_joinery_schedule_seeded.csv"
    proposal = columns.propose(columns.read_rows(path), Side.ARCHITECT)
    hand = schedule.load_mapping(path.with_suffix(".mapping.yaml"))
    assert elements(path, proposal["mapping"], Side.ARCHITECT) == elements(
        path, hand, Side.ARCHITECT
    )
    assert proposal["mapping"]["props"]["fire_rating_min"]["default"] == 0


def test_export_proposal_reads_the_same_as_the_hand_mapping():
    path = FIX / "erp" / "duplex_erp_export_seeded.csv"
    proposal = columns.propose(columns.read_rows(path), Side.ERP)
    hand = erp_table.load_mapping(path.with_suffix(".mapping.yaml"))
    assert proposal["mapping"]["type"]["column"] == "Artikelsoort"
    assert elements(path, proposal["mapping"], Side.ERP) == elements(path, hand, Side.ERP)


def test_header_row_found_below_title_lines():
    rows = [["Kozijnstaat project X"], [], ["Pos.", "Aantal", "Breedte (cm)", "Hoogte (cm)"],
            ["K1", 2, 120, 150]]  # fmt: skip
    proposal = columns.propose(rows, Side.ARCHITECT)
    assert proposal["header_row"] == 3
    assert proposal["mapping"]["units"] == "cm"
    assert proposal["mapping"]["columns"] == {"mark": "Pos.", "quantity": "Aantal",
                                              "width_mm": "Breedte (cm)",
                                              "height_mm": "Hoogte (cm)"}  # fmt: skip
    assert proposal["sample"] == [["K1", "2", "120", "150"]]


def test_metres_recognised_from_the_values():
    rows = [["Mark", "Width", "Height"], ["A", "1.2", "2.4"], ["B", "0.9", "2.1"]]
    assert columns.propose(rows, Side.ARCHITECT)["mapping"]["units"] == "m"


def test_unknown_headers_give_an_empty_proposal_not_a_guess():
    rows = [["Foo", "Bar"], ["1", "2"]]
    proposal = columns.propose(rows, Side.ERP)
    assert proposal["mapping"]["columns"] == {}
    assert proposal["mapping"]["type"] == "frame"
    assert "props" not in proposal["mapping"]


def test_fire_rating_empty_means_none_when_the_column_exists():
    rows = [["Merk", "Brandwerendheid"], ["A", ""], ["B", ""]]
    spec = columns.propose(rows, Side.ERP)["mapping"]["props"]["fire_rating_min"]
    assert spec["default"] == 0


def test_fits_compares_headers_like_the_parser():
    mapping = {"type": "frame", "columns": {"mark": "Merk", "width_mm": "Breedte"}}
    assert columns.fits(mapping, ["merk ", "BREEDTE", "Hoogte"])
    assert not columns.fits(mapping, ["Merk", "Hoogte"])
    assert not columns.fits({"type": "frame", "columns": {}}, ["Merk"])


def test_yaml_is_checked_and_loads_back(tmp_path):
    path = FIX / "schedule" / "duplex_joinery_schedule.csv"
    mapping = columns.propose(columns.read_rows(path), Side.ARCHITECT)["mapping"]
    out = tmp_path / "s.mapping.yaml"
    out.write_text(columns.to_yaml(mapping, out.name))
    assert schedule.load_mapping(out) == mapping
    bad = dict(mapping, units="inch")
    try:
        columns.to_yaml(bad, "x")
    except ValueError as exc:
        assert "units" in str(exc)
    else:
        raise AssertionError("bad units accepted")
