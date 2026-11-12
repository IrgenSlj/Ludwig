import json
from pathlib import Path

import pytest

from ludwig.model import Element, ElementType, Severity, Side, SourceKind, SourceRef, Status
from ludwig.rules import engine, fixtures
from ludwig.rules.packs import load_pack

DEMO = Path(__file__).resolve().parent / "packs" / "demo"


@pytest.fixture(scope="module")
def pack():
    return load_pack(DEMO)


def sash(mark, width, **kw):
    src = SourceRef("erp.csv", SourceKind.ERP, cell=f"C{mark[-1]}")
    return Element(f"e-{mark}", Side.ERP, ElementType.WINDOW_SASH, [src], mark=mark,
                   width_mm=width, **kw)  # fmt: skip


def by_rule(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


def test_every_demo_rule_passes_and_fails_on_its_fixtures(pack):
    assert fixtures.check(pack) == []


@pytest.mark.parametrize(
    ("width", "status"), [(1400.0, Status.PASS), (1500.0, Status.PASS), (1650.0, Status.FAIL)]
)
def test_require_rule_status(pack, width, status):
    (finding,) = by_rule(engine.run([sash("R1", width)], pack), "sash-width-max")
    assert finding.status is status
    assert finding.measured == width
    assert finding.expected == "width_mm <= 1500"
    assert finding.severity is Severity.BLOCKER


def test_fail_message_and_evidence(pack):
    el = sash("R1", 1650.0)
    (finding,) = by_rule(engine.run([el], pack), "sash-width-max")
    assert finding.message == "Sash R1: width 1650 mm exceeds machine limit 1500 mm"
    assert finding.evidence == [el.sources[0]]
    assert finding.element_ids == ["e-R1"] and finding.mark == "R1"
    assert (finding.pack, finding.pack_version) == ("demo", "0.0.1")


def test_missing_value_is_not_checked_never_pass(pack):
    (finding,) = by_rule(engine.run([sash("R1", None)], pack), "sash-width-max")
    assert finding.status is Status.NOT_CHECKED
    assert finding.reason == "width_mm is not set"


def test_rule_scope_skips_other_sides_and_types(pack):
    arch = Element("a", Side.ARCHITECT, ElementType.WINDOW_SASH,
                   [SourceRef("m.ifc", SourceKind.IFC)], width_mm=9999.0)  # fmt: skip
    assert by_rule(engine.run([arch], pack), "sash-width-max") == []


def door(props):
    src = SourceRef("m.ifc", SourceKind.IFC, ifc_guid="g")
    return Element("d", Side.ARCHITECT, ElementType.DOOR_LEAF, [src], mark="D1", props=props)


def test_when_false_is_not_applicable(pack):
    (f,) = by_rule(engine.run([door({"fire_rating_min": 0.0})], pack), "fire-door-sound")
    assert f.status is Status.NOT_APPLICABLE


def test_when_that_cannot_be_evaluated_is_not_checked(pack):
    (f,) = by_rule(engine.run([door({})], pack), "fire-door-sound")
    assert f.status is Status.NOT_CHECKED
    assert f.reason == "when: props.fire_rating_min is not set"


def test_props_and_message_placeholders(pack):
    (f,) = by_rule(
        engine.run([door({"fire_rating_min": 60.0, "sound_reduction_db": 25.5})], pack),
        "fire-door-sound",
    )
    assert f.status is Status.FAIL
    assert f.message == "Door D1: 25.5 dB, fire-rated doors need 30 dB"
    assert f.measured == 25.5


def test_type_mismatch_is_not_checked(pack):
    (f,) = by_rule(
        engine.run([door({"fire_rating_min": 60.0, "sound_reduction_db": "high"})], pack),
        "fire-door-sound",
    )
    assert f.status is Status.NOT_CHECKED and "cannot compare" in f.reason


def write_pack(tmp_path, checks):
    (tmp_path / "pack.yaml").write_text("name: t\nversion: '1'\n")
    (tmp_path / "checks.yaml").write_text(checks)
    return load_pack(tmp_path)


def test_parent_fields_are_readable(tmp_path):
    pack = write_pack(
        tmp_path,
        "- id: sash-fits\n  kind: require\n  severity: blocker\n"
        "  applies_to: {type: window_sash}\n  require: width_mm < parent.width_mm\n",
    )
    frame_src = SourceRef("erp.csv", SourceKind.ERP, cell="A1")
    frame = Element("f1", Side.ERP, ElementType.FRAME, [frame_src], mark="K1", width_mm=1000.0)
    inside = sash("R1", 900.0, parent_id="f1")
    orphan = sash("R2", 900.0)
    findings = engine.run([frame, inside, orphan], pack).findings
    assert [(f.mark, f.status) for f in findings] == [
        ("R1", Status.PASS), ("R2", Status.NOT_CHECKED)
    ]  # fmt: skip
    assert findings[0].evidence == [inside.sources[0], frame_src]
    assert findings[1].reason == "parent.width_mm is not set"


def test_coverage_numbers(pack):
    result = engine.run([sash("R1", 1650.0), sash("R2", None), door({"fire_rating_min": 0.0})],
                        pack)  # fmt: skip
    assert (result.rules_run, result.elements_total, result.elements_covered) == (3, 3, 2)
    assert result.not_checked == 1


def test_run_is_deterministic(pack):
    els = [sash("R1", 1650.0), sash("R2", 1200.0), door({"fire_rating_min": 60.0})]
    a = json.dumps([f.to_dict() for f in engine.run(els, pack).findings])
    b = json.dumps([f.to_dict() for f in engine.run(els, pack).findings])
    assert a == b


@pytest.mark.parametrize(
    ("value", "text"), [(1200.0, "1200"), (1172.5, "1172.5"), (None, "not set"), (True, "true"),
                        ("HR++", "HR++"), (4, "4")],
)  # fmt: skip
def test_format_value(value, text):
    assert engine.format_value(value) == text


def test_fixture_check_reports_a_rule_that_does_not_fail(tmp_path):
    pack = write_pack(tmp_path, "- id: r\n  kind: require\n  severity: info\n"
                      "  require: width_mm > 0\n")  # fmt: skip
    folder = tmp_path / "fixtures" / "r"
    folder.mkdir(parents=True)
    body = {"elements": [{"side": "erp", "type": "frame", "width_mm": 5}]}
    (folder / "pass.json").write_text(json.dumps(body))
    (folder / "fail.json").write_text(json.dumps(body))
    assert fixtures.check(pack) == ["r: fail.json should fail, got [<Status.PASS: 'pass'>]"]
