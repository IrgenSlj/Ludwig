from pathlib import Path

import pytest

from ludwig.adapters import erp_table
from ludwig.match import pairs
from ludwig.model import Element, ElementType, Side, SourceKind, SourceRef, Status
from ludwig.parsers import ifc
from ludwig.rules import engine, fixtures
from ludwig.rules.packs import load_pack

ROOT = Path(__file__).resolve().parent.parent
PACK = Path(__file__).resolve().parent / "packs" / "reconcile"
ERP = ROOT / "fixtures" / "erp" / "duplex_erp_export.csv"


@pytest.fixture(scope="module")
def pack():
    return load_pack(PACK)


def run(elements, pack):
    return engine.run(elements, pack, pairs(elements, pack.match_tolerance_mm))


def frame(eid, side, file, **kw):
    kind = SourceKind.ERP if side is Side.ERP else SourceKind.SHEET
    return Element(eid, side, ElementType.FRAME, [SourceRef(file, kind, cell="A1")], mark="K1",
                   field_sources={k: SourceRef(file, kind, cell=k) for k in kw}, **kw)  # fmt: skip


def by_rule(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


def test_every_compare_rule_passes_and_fails_on_its_fixtures(pack):
    assert fixtures.check(pack) == []


def test_fail_shows_both_values_and_both_sources(pack):
    result = run([frame("a", Side.ARCHITECT, "s.csv", width_mm=1200.0),
                  frame("e", Side.ERP, "erp.csv", width_mm=1180.0)], pack)  # fmt: skip
    [f] = by_rule(result, "width-matches")
    assert f.status is Status.FAIL
    assert f.measured == {"architect.width_mm": {"s.csv": 1200.0},
                          "erp.width_mm": {"erp.csv": 1180.0}}  # fmt: skip
    assert f.expected == "architect.width_mm == erp.width_mm (within 1)"
    assert f.message == "Frame K1: width 1200 in the drawings, 1180 in production"
    assert [(s.file, s.cell) for s in f.evidence] == [("s.csv", "width_mm"),
                                                     ("erp.csv", "width_mm")]  # fmt: skip
    assert f.element_ids == ["a", "e"]


def test_quantity_compares_each_document_total_with_the_erp_total(pack):
    elements = [frame("m", Side.ARCHITECT, "m.ifc", quantity=4),
                frame("s", Side.ARCHITECT, "s.csv", quantity=3),
                frame("e", Side.ERP, "erp.csv", quantity=4)]  # fmt: skip
    [f] = by_rule(run(elements, pack), "quantity-matches")
    assert f.status is Status.FAIL
    assert f.message == "mark K1: quantity differs: m.ifc 4, s.csv 3 vs 4"


def test_missing_values_are_not_checked(pack):
    no_erp = run([frame("a", Side.ARCHITECT, "s.csv", width_mm=1200.0),
                  frame("e", Side.ERP, "erp.csv", width_mm=None),
                  frame("e2", Side.ERP, "erp.csv", width_mm=1200.0)], pack)  # fmt: skip
    [f] = by_rule(no_erp, "width-matches")
    assert (f.status, f.reason) == (Status.NOT_CHECKED, "erp.width_mm is not set in erp.csv")
    no_arch = run([frame("a", Side.ARCHITECT, "s.csv", width_mm=None),
                   frame("e", Side.ERP, "erp.csv", width_mm=1200.0)], pack)  # fmt: skip
    [f] = by_rule(no_arch, "width-matches")
    assert (f.status, f.reason) == (Status.NOT_CHECKED, "architect.width_mm is not set")


def test_architect_gap_in_one_document_still_compares_the_stated_value(pack):
    result = run([frame("m", Side.ARCHITECT, "m.ifc", width_mm=None),
                  frame("s", Side.ARCHITECT, "s.csv", width_mm=1200.0),
                  frame("e", Side.ERP, "erp.csv", width_mm=1200.0)], pack)  # fmt: skip
    assert [f.status for f in by_rule(result, "width-matches")] == [Status.PASS]


def test_when_false_is_not_applicable_and_unmatched_gives_no_compare(pack):
    result = run([frame("a", Side.ARCHITECT, "s.csv"), frame("e", Side.ERP, "erp.csv")], pack)
    assert [f.status for f in by_rule(result, "glazing-matches")] == [Status.NOT_APPLICABLE]
    lonely = run([frame("a", Side.ARCHITECT, "s.csv", width_mm=1.0),
                  Element("e", Side.ERP, ElementType.FRAME, [SourceRef("erp.csv", SourceKind.ERP)],
                          mark="K2", width_mm=1.0)], pack)  # fmt: skip
    assert by_rule(lonely, "width-matches") == []


def test_mixed_kinds_are_not_checked(pack):
    result = run([frame("a", Side.ARCHITECT, "s.csv", props={"glazing_type": "HR++"}),
                  frame("e", Side.ERP, "erp.csv", props={"glazing_type": 2.0})], pack)  # fmt: skip
    [f] = by_rule(result, "glazing-matches")
    assert f.reason == "values of different kinds cannot be compared"


def test_without_production_data_compare_rules_are_not_checked(pack):
    result = run([frame("a", Side.ARCHITECT, "s.csv", width_mm=1.0)], pack)
    assert {(f.status, f.reason) for f in result.findings} == {
        (Status.NOT_CHECKED, "no production data given")}  # fmt: skip


def test_duplex_model_agrees_with_the_invented_export(pack):
    elements, _ = ifc.parse(ROOT / "fixtures" / "ifc" / "duplex_architectural_ifc2x3.ifc")
    found, _ = erp_table.parse(ERP, erp_table.load_mapping(ERP.with_suffix(".mapping.yaml")))
    result = run(elements + found, pack)
    statuses = {(f.rule_id, f.status) for f in result.findings}
    assert (("width-matches", Status.PASS) in statuses
            and ("quantity-matches", Status.PASS) in statuses)  # fmt: skip
    assert not [f for f in result.findings if f.status is Status.FAIL]


def test_ambiguous_position_is_not_checked(pack):
    def loose(eid, side):
        kind = SourceKind.ERP if side is Side.ERP else SourceKind.SHEET
        return Element(eid, side, ElementType.FRAME, [SourceRef("f", kind)], width_mm=900.0,
                       height_mm=2100.0)  # fmt: skip

    result = run([loose("a1", Side.ARCHITECT), loose("a2", Side.ARCHITECT), loose("e", Side.ERP)],
                 pack)  # fmt: skip
    [f] = by_rule(result, "width-matches")
    assert f.status is Status.NOT_CHECKED and f.reason.startswith("ambiguous match")
    assert f.message.startswith("width-matches: unmarked frame 900 x 2100")


def test_count_per_value_must_agree_when_a_mark_has_several_values(pack):
    def door(eid, side, file, qty, glass):
        return frame(eid, side, file, quantity=qty, props={"glazing_type": glass})

    same = [
        door("a", Side.ARCHITECT, "s.csv", 2, "HR++"),
        door("b", Side.ARCHITECT, "s.csv", 2, "Triple"),
        door("e", Side.ERP, "erp.csv", 2, "HR++"),
        door("f", Side.ERP, "erp.csv", 2, "triple"),
    ]
    assert [f.status for f in by_rule(run(same, pack), "glazing-matches")] == [Status.PASS]
    skewed = [
        *same[:2],
        door("e", Side.ERP, "erp.csv", 3, "HR++"),
        door("f", Side.ERP, "erp.csv", 1, "Triple"),
    ]
    [f] = by_rule(run(skewed, pack), "glazing-matches")
    assert f.status is Status.FAIL
    assert f.measured["erp.props.glazing_type"] == {"erp.csv": {"HR++": 3, "Triple": 1}}


def test_evidence_leaves_out_elements_without_the_value(pack):
    elements = [frame("m", Side.ARCHITECT, "plan.dxf", props={}),
                frame("s", Side.ARCHITECT, "s.csv", props={"glazing_type": "HR++"}),
                frame("e", Side.ERP, "erp.csv", props={"glazing_type": "Triple"})]  # fmt: skip
    result = run(elements, pack)
    [f] = by_rule(result, "glazing-matches")
    assert {s.file for s in f.evidence} == {"s.csv", "erp.csv"}
