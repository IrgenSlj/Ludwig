import json

import pytest

from ludwig.model import (
    Element,
    ElementType,
    Finding,
    ParseWarning,
    Severity,
    Side,
    SourceKind,
    SourceRef,
    Status,
    normalise_mark,
)


def _json_round_trip(obj):
    return type(obj).from_dict(json.loads(json.dumps(obj.to_dict())))


IFC_SRC = SourceRef("model.ifc", SourceKind.IFC, ifc_guid="2O2Fr$t4X7Zf8NOew3FLOH")
SHEET_SRC = SourceRef("schedule.xlsx", SourceKind.SHEET, sheet="Kozijnen", cell="D7")
PDF_SRC = SourceRef("set.pdf", SourceKind.PDF, page=3, bbox=(10.0, 20.5, 110.0, 40.0))


def test_element_round_trips_through_json():
    el = Element(
        id="a1",
        side=Side.ARCHITECT,
        type=ElementType.FRAME,
        sources=[IFC_SRC],
        mark=" k 01 ",
        quantity=2,
        width_mm=1200.0,
        height_mm=None,
        location="00",
        props={"fire_rating_min": 30, "glazing_type": "HR++"},
        field_sources={"width_mm": SHEET_SRC},
    )
    assert _json_round_trip(el) == el
    assert el.mark == "K01"


def test_finding_round_trips_through_json():
    f = Finding(
        rule_id="sash-width-max",
        pack="joinery-nl",
        pack_version="0.1.0",
        status=Status.FAIL,
        severity=Severity.BLOCKER,
        element_ids=["e1"],
        mark="K01",
        measured=1650.0,
        expected=1500.0,
        message="Sash K01: width 1650 mm exceeds machine limit 1500 mm",
        evidence=[IFC_SRC, PDF_SRC],
    )
    assert _json_round_trip(f) == f


def test_parse_warning_round_trips_through_json():
    w = ParseWarning("schedule.xlsx", "column 'Breedte' not found", SHEET_SRC)
    assert _json_round_trip(w) == w
    assert _json_round_trip(ParseWarning("x.ifc", "unreadable")) == ParseWarning(
        "x.ifc", "unreadable"
    )


def test_source_ref_omits_unset_locators():
    assert SHEET_SRC.to_dict() == {
        "file": "schedule.xlsx",
        "kind": "sheet",
        "sheet": "Kozijnen",
        "cell": "D7",
    }


def test_not_checked_requires_a_reason():
    with pytest.raises(ValueError):
        Finding("r", "p", "1", Status.NOT_CHECKED, Severity.WARNING, ["e1"])
    Finding("r", "p", "1", Status.NOT_CHECKED, Severity.WARNING, ["e1"], reason="width missing")


def test_element_requires_a_source():
    with pytest.raises(ValueError):
        Element(id="x", side=Side.ERP, type=ElementType.FRAME, sources=[])


def test_source_of_falls_back_to_the_element_source():
    el = Element("a", Side.ERP, ElementType.FRAME, [IFC_SRC], field_sources={"mark": SHEET_SRC})
    assert el.source_of("mark") == SHEET_SRC
    assert el.source_of("width_mm") == IFC_SRC


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(" k 01 ", "K01"), ("K-01", "K-01"), ("", None), ("   ", None), (None, None), (12, "12")],
)
def test_normalise_mark(raw, expected):
    assert normalise_mark(raw) == expected
