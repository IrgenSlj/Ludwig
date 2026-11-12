from collections import Counter
from pathlib import Path

import pytest

from ludwig.model import ElementType, Side
from ludwig.parsers import ifc

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "ifc"
DUPLEX = FIXTURES / "duplex_architectural_ifc2x3.ifc"
CLINIC = FIXTURES / "clinic_architectural_ifc2x3.ifc"


def _quantity_by_mark(elements):
    counts: Counter = Counter()
    for el in elements:
        counts[el.mark] += el.quantity
    return dict(counts)


@pytest.fixture(scope="module")
def duplex():
    return ifc.parse(DUPLEX)


@pytest.fixture(scope="module")
def clinic():
    return ifc.parse(CLINIC)


def test_duplex_quantity_by_mark_matches_hand_count(duplex):
    elements, _ = duplex
    # Hand count from the model's Type Mark values: windows 01..05 and 36 (24 in all),
    # doors 28, 32, 33, 56 (14 in all).
    assert _quantity_by_mark(elements) == {
        "01": 4, "02": 8, "03": 4, "04": 4, "05": 2, "36": 2,
        "28": 4, "32": 6, "33": 2, "56": 2,
    }  # fmt: skip
    assert sum(e.quantity for e in elements) == 38
    assert all(e.side is Side.ARCHITECT and e.type is ElementType.FRAME for e in elements)


def test_clinic_quantity_by_mark_matches_hand_count(clinic):
    elements, _ = clinic
    # 58 windows, all Type Mark 19; 254 doors over 13 type marks.
    counts = _quantity_by_mark(elements)
    assert counts["19"] == 58
    assert counts["20"] == 215
    assert sum(counts.values()) == 58 + 254


def test_dimensions_are_millimetres_from_metre_models(duplex):
    elements, _ = duplex
    mark05 = [e for e in elements if e.mark == "05"]
    assert [(e.width_mm, e.height_mm) for e in mark05] == [(4835.0, 2420.0)]


def test_one_mark_with_two_sizes_stays_two_elements(clinic):
    elements, _ = clinic
    mark37 = sorted((e.width_mm, e.quantity) for e in clinic[0] if e.mark == "37")
    assert mark37 == [(899.5, 2), (901.0, 2)]  # checked against OverallWidth per GlobalId
    assert len(elements) > 14


def test_every_element_points_at_its_occurrences(duplex):
    elements, _ = duplex
    for el in elements:
        assert len(el.sources) == el.quantity
        assert all(s.ifc_guid and s.file == str(DUPLEX) for s in el.sources)


def test_revit_placeholder_values_are_not_set_and_reported(duplex):
    elements, warnings = duplex
    assert not any("fire_rating_min" in e.props for e in elements)
    assert any("FireRating" in w.message and "read as not set" in w.message for w in warnings)


def test_opening_direction_comes_from_the_type(duplex):
    elements, _ = duplex
    doors = [e for e in elements if e.mark in {"28", "32", "33", "56"}]
    by_mark = sorted((e.mark, e.location, e.props["opening_direction"]) for e in doors)
    assert by_mark == [("28", "Level 1", "left"), ("28", "Level 2", "right"),
                       ("32", "Level 2", "left"), ("32", "Level 2", "right"),
                       ("33", "Level 1", "right"), ("56", "Level 1", "left")]  # fmt: skip
    assert not any("opening_direction" in e.props for e in elements if e.mark == "01")


def test_unreadable_file_gives_a_warning_not_an_exception(tmp_path):
    bad = tmp_path / "broken.ifc"
    bad.write_text("not an ifc file")
    elements, warnings = ifc.parse(bad)
    assert elements == []
    assert len(warnings) == 1 and "cannot read IFC file" in warnings[0].message
    assert ifc.parse(tmp_path / "missing.ifc")[1]


def test_mapping_rejects_unknown_keys(tmp_path):
    m = tmp_path / "m.yaml"
    m.write_text("classes: {IfcWindow: frame}\nmarks: []\n")
    with pytest.raises(ValueError, match="unknown keys"):
        ifc.load_mapping(m)


def test_parse_is_deterministic(duplex):
    again, _ = ifc.parse(DUPLEX)
    assert [e.to_dict() for e in again] == [e.to_dict() for e in duplex[0]]


def test_spaced_revit_placeholder_is_not_set_either(clinic):
    elements, warnings = clinic
    assert not any("not a number" in w.message for w in warnings)
    assert any("Pset_DoorCommon.FireRating" in w.message and "read as not set" in w.message
               for w in warnings)  # fmt: skip
