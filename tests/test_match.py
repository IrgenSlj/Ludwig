from pathlib import Path

from ludwig.adapters import erp_table
from ludwig.match import match
from ludwig.model import Element, ElementType, MatchStatus, Side, SourceKind, SourceRef
from ludwig.parsers import ifc, schedule

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"


def el(eid, side, mark=None, w=1000.0, h=2000.0, location=None, etype=ElementType.FRAME):
    kind = SourceKind.ERP if side is Side.ERP else SourceKind.IFC
    return Element(eid, side, etype, [SourceRef(f"{side}.x", kind)], mark=mark,
                   width_mm=w, height_mm=h, location=location)  # fmt: skip


A, E = Side.ARCHITECT, Side.ERP


def statuses(matches):
    return sorted((m.status.value, [e.id for e in m.elements]) for m in matches)


def test_exact_by_type_and_mark_groups_all_documents():
    ms = match([el("ifc", A, "K1"), el("sched", A, "K1", w=990.0), el("erp1", E, "K1"),
                el("erp2", E, "K1")])  # fmt: skip
    assert statuses(ms) == [("matched", ["ifc", "sched", "erp1", "erp2"])]
    assert ms[0].by == "mark" and ms[0].mark == "K1"


def test_same_mark_different_type_does_not_match():
    ms = match([el("a", A, "K1"), el("e", E, "K1", etype=ElementType.WINDOW_SASH)])
    assert statuses(ms) == [("missing_in_erp", ["a"]), ("not_in_architect_set", ["e"])]


def test_fallback_by_location_and_size_when_a_mark_is_missing():
    ms = match([el("a", A, "K1", location="Level 1"), el("e", E, None, w=1000.4,
                location="level 1 ")], tolerance_mm=0.5)  # fmt: skip
    assert statuses(ms) == [("matched", ["a", "e"])]
    assert ms[0].by == "fallback" and ms[0].mark == "K1"


def test_fallback_respects_tolerance_location_and_missing_sizes():
    assert statuses(match([el("a", A), el("e", E, w=1001.0)], tolerance_mm=0.5)) == [
        ("missing_in_erp", ["a"]), ("not_in_architect_set", ["e"])]  # fmt: skip
    assert statuses(match([el("a", A, location="L1"), el("e", E, location="L2")])) == [
        ("missing_in_erp", ["a"]), ("not_in_architect_set", ["e"])]  # fmt: skip
    assert statuses(match([el("a", A, w=None), el("e", E, w=None)])) == [
        ("missing_in_erp", ["a"]), ("not_in_architect_set", ["e"])]  # fmt: skip


def test_two_different_marks_never_fallback_match():
    ms = match([el("a", A, "K1"), el("e", E, "K2")])
    assert statuses(ms) == [("missing_in_erp", ["a"]), ("not_in_architect_set", ["e"])]


def test_unmatched_on_either_side():
    ms = match([el("a", A, "K1"), el("b", A, "K2"), el("e", E, "K2"), el("f", E, "K9")])
    assert statuses(ms) == [("matched", ["b", "e"]), ("missing_in_erp", ["a"]),
                            ("not_in_architect_set", ["f"])]  # fmt: skip


def test_several_candidates_are_ambiguous_not_guessed():
    ms = match([el("a1", A), el("a2", A), el("e", E)])
    assert statuses(ms) == [("ambiguous", ["a1", "a2", "e"])]
    chain = match([el("a1", A), el("e1", E), el("a2", A, w=1000.4), el("e2", E, w=1000.8)],
                  tolerance_mm=0.5)  # fmt: skip
    assert [m.status for m in chain] == [MatchStatus.AMBIGUOUS]


def test_duplex_model_and_schedule_match_the_export_by_mark():
    elements, _ = ifc.parse(FIX / "ifc" / "duplex_architectural_ifc2x3.ifc")
    sched = FIX / "schedule" / "duplex_joinery_schedule.csv"
    found, _ = schedule.parse(sched, schedule.load_mapping(sched.with_suffix(".mapping.yaml")))
    elements += found
    export = FIX / "erp" / "duplex_erp_export.csv"
    found, _ = erp_table.parse(export, erp_table.load_mapping(
        export.with_suffix(".mapping.yaml")))  # fmt: skip
    elements += found
    ms = match(elements)
    assert {m.status for m in ms} == {MatchStatus.MATCHED}
    assert sorted(m.mark for m in ms) == ["01", "02", "03", "04", "05", "28", "32", "33",
                                          "36", "56"]  # fmt: skip
    assert all(m.by == "mark" for m in ms)
