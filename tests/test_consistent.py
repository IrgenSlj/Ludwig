from pathlib import Path

import pytest

from ludwig.model import Element, ElementType, Side, SourceKind, SourceRef, Status
from ludwig.parsers import ifc, schedule
from ludwig.rules import engine
from ludwig.rules.packs import load_pack

ROOT = Path(__file__).resolve().parent.parent
DUPLEX = ROOT / "fixtures" / "ifc" / "duplex_architectural_ifc2x3.ifc"
CLINIC = ROOT / "fixtures" / "ifc" / "clinic_architectural_ifc2x3.ifc"
SCHED = ROOT / "fixtures" / "schedule"

CHECKS = """\
- id: count-per-mark
  kind: consistent
  applies_to: {side: architect, type: frame}
  group_by: mark
  field: quantity
  severity: warning
- id: width-per-mark
  kind: consistent
  applies_to: {side: architect, type: frame}
  group_by: mark
  field: width_mm
  tolerance: 0.5
  severity: blocker
- id: height-per-mark
  kind: consistent
  applies_to: {side: architect, type: frame}
  group_by: mark
  field: height_mm
  severity: blocker
"""


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    root = tmp_path_factory.mktemp("pack")
    (root / "pack.yaml").write_text("name: t\nversion: '1'\n")
    (root / "checks.yaml").write_text(CHECKS)
    return load_pack(root)


def table(*paths):
    elements = []
    for path in paths:
        if path.suffix == ".ifc":
            found, _ = ifc.parse(path)
        else:
            found, _ = schedule.parse(path, schedule.load_mapping(
                path.with_name(f"{path.stem}.mapping.yaml")))  # fmt: skip
        elements.extend(found)
    return elements


def fails(result):
    return sorted((f.rule_id, f.mark) for f in result.findings if f.status is Status.FAIL)


def test_model_and_matching_schedule_agree(pack):
    result = engine.run(table(DUPLEX, SCHED / "duplex_joinery_schedule.csv"), pack)
    assert fails(result) == []
    statuses = {f.status for f in result.findings}
    assert statuses == {Status.PASS}
    assert len([f for f in result.findings if f.rule_id == "count-per-mark"]) == 10


def test_model_and_seeded_schedule_disagree_where_seeded(pack):
    result = engine.run(table(DUPLEX, SCHED / "duplex_joinery_schedule_seeded.csv"), pack)
    assert fails(result) == [
        ("count-per-mark", "02"),  # 8 in the model, 7 in the schedule
        ("count-per-mark", "56"),  # row removed from the schedule
        ("width-per-mark", "05"),  # 4835 vs 4800
    ]
    by_key = {(f.rule_id, f.mark): f for f in result.findings}
    count02 = by_key[("count-per-mark", "02")]
    seeded = str(SCHED / "duplex_joinery_schedule_seeded.csv")
    assert count02.measured == {str(DUPLEX): 8, seeded: 7}
    assert count02.message == (
        "mark 02: quantity differs: duplex_architectural_ifc2x3.ifc 8, "
        "duplex_joinery_schedule_seeded.csv 7"
    )
    kinds = {s.kind for s in count02.evidence}
    assert kinds == {SourceKind.IFC, SourceKind.SHEET}
    assert len([s for s in count02.evidence if s.kind is SourceKind.IFC]) == 8
    width05 = by_key[("width-per-mark", "05")]
    assert width05.expected == "one value (within 0.5)"
    assert width05.severity.value == "blocker"


def test_one_mark_with_two_widths_in_one_model_fails(pack):
    result = engine.run(table(CLINIC), pack)
    assert ("width-per-mark", "37") in fails(result)
    count = [f for f in result.findings if f.rule_id == "count-per-mark"]
    assert {f.status for f in count} == {Status.NOT_APPLICABLE}  # one document: nothing to compare


def _frame(eid, file, mark, quantity=1, width=1000.0):
    kind = SourceKind.IFC if file.endswith(".ifc") else SourceKind.SHEET
    return Element(eid, Side.ARCHITECT, ElementType.FRAME, [SourceRef(file, kind)], mark=mark,
                   quantity=quantity, width_mm=width)  # fmt: skip


def test_missing_mark_or_value_is_not_checked(pack):
    elements = [
        _frame("a", "m.ifc", None),
        _frame("b", "m.ifc", "K1", width=None),
        _frame("c", "s.csv", "K1", quantity=None),
    ]
    result = engine.run(elements, pack)
    nc = {(f.rule_id, tuple(f.element_ids)): f.reason for f in result.findings
          if f.status is Status.NOT_CHECKED}  # fmt: skip
    assert nc[("count-per-mark", ("a",))] == "mark is not set"
    assert nc[("count-per-mark", ("b", "c"))] == "quantity is not set in s.csv"
    assert nc[("width-per-mark", ("b", "c"))] == "width_mm is not set in m.ifc"


def test_tolerance_allows_small_differences(pack):
    ok = engine.run([_frame("a", "m.ifc", "K1", width=1000.0),
                     _frame("b", "s.csv", "K1", width=1000.4)], pack)  # fmt: skip
    assert fails(ok) == []
    off = engine.run([_frame("a", "m.ifc", "K1", width=1000.0),
                      _frame("b", "s.csv", "K1", width=1000.6)], pack)  # fmt: skip
    assert fails(off) == [("width-per-mark", "K1")]
