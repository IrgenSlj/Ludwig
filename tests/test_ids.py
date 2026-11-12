"""IDS facets against element facts (PLAN 4.1): a pass and a fail case per facet."""

import shutil
from pathlib import Path

import pytest

from ludwig.model import Element, ElementType, Side, SourceKind, SourceRef, Status
from ludwig.parsers import ifc
from ludwig.rules import ids

ROOT = Path(__file__).resolve().parent.parent
HEAD = ('<ids xmlns="http://standards.buildingsmart.org/IDS" '
        'xmlns:xs="http://www.w3.org/2001/XMLSchema"><specifications>')  # fmt: skip


DOORS = "<entity><name><simpleValue>IFCDOOR</simpleValue></name></entity>"


def spec(requirements, applicability=DOORS, occurs=""):
    return (
        f'{HEAD}<specification name="S"><applicability{occurs}>{applicability}</applicability>'
        f"<requirements>{requirements}</requirements></specification></specifications></ids>"
    )


def facts(**kw):
    base = {"entity": "IFCDOOR", "predefined_type": "DOOR", "attributes": {"Name": "D1",
            "OverallWidth": 0.9}, "properties": {"Pset_DoorCommon": {"FireRating": "EI30",
            "IsExternal": False}}, "classification": [["NL-SfB", "32.31"]],
            "material": ["Hout", "Wood"], "unit_scale_m": 1.0}  # fmt: skip
    base.update(kw)
    return base


def door(*occurrence_facts, mark="D1"):
    sources = [SourceRef("m.ifc", SourceKind.IFC, ifc_guid=f"g{i}")
               for i in range(len(occurrence_facts))]  # fmt: skip
    return Element(f"m.ifc#{mark}", Side.ARCHITECT, ElementType.FRAME, sources, mark=mark,
                   quantity=len(sources), facts=list(occurrence_facts))  # fmt: skip


def evaluate(tmp_path, xml, *elements):
    path = tmp_path / "r.ids"
    path.write_text(xml)
    return ids.run(ids.load(path), list(elements), "p", "1")


def statuses(findings):
    return [f.status for f in findings if f.element_ids]


V = "<value><simpleValue>{}</simpleValue></value>"
PROP = ("<property{dt}><propertySet><simpleValue>Pset_DoorCommon</simpleValue></propertySet>"
        "<baseName><simpleValue>{name}</simpleValue></baseName>{value}</property>")  # fmt: skip


@pytest.mark.parametrize(("requirement", "expected"), [
    ("<entity><name><simpleValue>IFCDOOR</simpleValue></name>"
     "<predefinedType><simpleValue>DOOR</simpleValue></predefinedType></entity>", Status.PASS),
    ("<entity><name><simpleValue>IFCDOOR</simpleValue></name>"
     "<predefinedType><simpleValue>GATE</simpleValue></predefinedType></entity>", Status.FAIL),
    ("<attribute><name><simpleValue>Name</simpleValue></name>" + V.format("D1") + "</attribute>",
     Status.PASS),
    ("<attribute><name><simpleValue>Description</simpleValue></name></attribute>", Status.FAIL),
    (PROP.format(dt="", name="FireRating", value=""), Status.PASS),
    (PROP.format(dt="", name="FireRating", value=V.format("EI60")), Status.FAIL),
    (PROP.format(dt=' dataType="IFCBOOLEAN"', name="IsExternal", value=V.format("false")),
     Status.PASS),
    (PROP.format(dt="", name="AcousticRating", value=""), Status.FAIL),
    ("<classification><value><simpleValue>32.31</simpleValue></value>"
     "<system><simpleValue>NL-SfB</simpleValue></system></classification>", Status.PASS),
    ("<classification><system><simpleValue>Uniclass</simpleValue></system></classification>",
     Status.FAIL),
    ("<material>" + V.format("Hout") + "</material>", Status.PASS),
    ("<material>" + V.format("Steel") + "</material>", Status.FAIL),
    ('<material cardinality="prohibited">' + V.format("Wood") + "</material>", Status.FAIL),
    ('<classification cardinality="optional"><system><simpleValue>Uniclass</simpleValue>'
     "</system></classification>", Status.PASS),
    ('<property cardinality="optional"><propertySet><simpleValue>Pset_DoorCommon</simpleValue>'
     "</propertySet><baseName><simpleValue>FireRating</simpleValue></baseName>"
     + V.format("EI60") + "</property>", Status.FAIL),
])  # fmt: skip
def test_facets_pass_and_fail(tmp_path, requirement, expected):
    assert statuses(evaluate(tmp_path, spec(requirement), door(facts()))) == [expected]


def restriction(*parts):
    body = "".join(f'<xs:{k} value="{v}"/>' for k, v in parts)
    return f'<value><xs:restriction base="xs:string">{body}</xs:restriction></value>'


@pytest.mark.parametrize(("value", "expected"), [
    (restriction(("enumeration", "EI30"), ("enumeration", "EI60")), Status.PASS),
    (restriction(("enumeration", "EI60")), Status.FAIL),
    (restriction(("pattern", "EI[0-9]+")), Status.PASS),
    (restriction(("pattern", "REI[0-9]+")), Status.FAIL),
    (restriction(("minLength", "3"), ("maxLength", "4")), Status.PASS),
    (restriction(("length", "5")), Status.FAIL),
])  # fmt: skip
def test_value_restrictions(tmp_path, value, expected):
    xml = spec(PROP.format(dt="", name="FireRating", value=value))
    assert statuses(evaluate(tmp_path, xml, door(facts()))) == [expected]


def test_bounds_on_lengths_use_si_units(tmp_path):
    width = ('<attribute><name><simpleValue>OverallWidth</simpleValue></name>'
             '<value><xs:restriction base="xs:double"><xs:minInclusive value="0.7"/>'
             '<xs:maxInclusive value="1.2"/></xs:restriction></value></attribute>')  # fmt: skip
    assert statuses(evaluate(tmp_path, spec(width), door(facts()))) == [Status.PASS]
    wide = facts(attributes={"OverallWidth": 1.25})
    [f] = evaluate(tmp_path, spec(width), door(wide))
    assert f.status is Status.FAIL and "is '1.25'" in f.message
    height = ('<property dataType="IFCLENGTHMEASURE"><propertySet><simpleValue>Pset_DoorCommon'
              '</simpleValue></propertySet><baseName><simpleValue>Height</simpleValue></baseName>'
              '<value><xs:restriction base="xs:double"><xs:maxInclusive value="2.4"/>'
              "</xs:restriction></value></property>")  # fmt: skip
    in_mm = facts(unit_scale_m=0.001, properties={"Pset_DoorCommon": {"Height": 2300.0}})
    assert statuses(evaluate(tmp_path, spec(height), door(in_mm))) == [Status.PASS]


def test_fail_names_the_failing_occurrences(tmp_path):
    xml = spec(PROP.format(dt="", name="FireRating", value=""))
    bare = facts(properties={"Pset_DoorCommon": {}})
    [f] = evaluate(tmp_path, xml, door(facts(), bare, bare))
    assert f.message == ("IDS 'S', mark D1: required property Pset_DoorCommon.FireRating: "
                         "missing (2 of 3 occurrences)")  # fmt: skip
    assert [s.ifc_guid for s in f.evidence] == ["g1", "g2"]


def test_unsupported_facets_and_restrictions_are_not_checked(tmp_path):
    part = ('<partOf relation="IFCRELAGGREGATES"><entity><name><simpleValue>IFCBUILDING'
            "</simpleValue></name></entity></partOf>")  # fmt: skip
    [f] = evaluate(tmp_path, spec(part), door(facts()))
    assert (f.status, f.reason) == (Status.NOT_CHECKED, "partOf facet is not supported")
    digits = PROP.format(dt="", name="FireRating", value=restriction(("totalDigits", "2")))
    [f] = evaluate(tmp_path, spec(digits), door(facts()))
    assert f.reason == "restriction xs:totalDigits is not supported"


def test_not_applicable_elements_get_no_finding(tmp_path):
    xml = spec(PROP.format(dt="", name="FireRating", value=""))
    assert evaluate(tmp_path, xml, door(facts(entity="IFCWINDOW"))) == []


def test_occurrence_limits_of_a_specification(tmp_path):
    xml = spec("", occurs=' minOccurs="1" maxOccurs="unbounded"')
    [f] = evaluate(tmp_path, xml, door(facts(entity="IFCWINDOW")))
    assert f.status is Status.FAIL and f.message.endswith("expected at least 1 applicable elements")
    none_allowed = spec("", occurs=' minOccurs="0" maxOccurs="0"')
    limit = [f for f in evaluate(tmp_path, none_allowed, door(facts())) if not f.element_ids]
    assert [f.status for f in limit] == [Status.FAIL]


def test_without_ifc_facts_every_specification_is_not_checked(tmp_path):
    sheet = Element("s", Side.ARCHITECT, ElementType.FRAME, [SourceRef("s.csv", SourceKind.SHEET)])
    [f] = evaluate(tmp_path, spec(PROP.format(dt="", name="FireRating", value="")), sheet)
    assert (f.status, f.reason) == (Status.NOT_CHECKED, "no IFC model in the input")


def test_bad_files_are_rejected(tmp_path):
    for body, problem in [("<x/>", "not an IDS file"),
                          (f"{HEAD}<specification><requirements/></specification>"
                           "</specifications></ids>", "has no applicability"),
                          ("<ids", "bad.ids")]:  # fmt: skip
        path = tmp_path / "bad.ids"
        path.write_text(body)
        with pytest.raises(ids.IdsError, match=problem):
            ids.load(path)


def test_duplex_model_against_the_invented_ids():
    specs = ids.load(ROOT / "tests" / "ids" / "duplex.ids")
    elements, _ = ifc.parse(ROOT / "fixtures" / "ifc" / "duplex_architectural_ifc2x3.ifc")
    found = ids.run(specs, elements, "p", "1")
    fails = sorted({(f.rule_id, f.mark) for f in found if f.status is Status.FAIL})
    assert ("ids-door-width-between-0-7-and-1-2-m", "33") in fails  # 1.25 m door
    assert ("ids-windows-are-external", "36") in fails  # roof light, IsExternal false
    assert {f.mark for f in found if f.rule_id == "ids-doors-have-a-fire-rating"
            and f.status is Status.FAIL} == {"28", "32", "33", "56"}  # fmt: skip
    assert {f.status for f in found if f.rule_id == "ids-doors-in-a-storey"} == {
        Status.NOT_CHECKED}  # fmt: skip


def test_pack_with_ids_runs_from_the_cli(tmp_path):
    import json

    from ludwig.cli import main
    from ludwig.rules.packs import load_pack

    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack.yaml").write_text("name: t\nversion: '1'\nfiles: {ids: req.ids}\n"
                                    "ids_severity: blocker\n")  # fmt: skip
    (pack / "checks.yaml").write_text("[]\n")
    shutil.copy(ROOT / "tests" / "ids" / "duplex.ids", pack / "req.ids")
    loaded = load_pack(pack)
    assert len(loaded.ids_specs) == 7
    out = tmp_path / "out"
    model = str(ROOT / "fixtures" / "ifc" / "duplex_architectural_ifc2x3.ifc")
    code = main(["check", "--architect", model, "--pack", str(pack), "--out", str(out)])
    report = json.loads((out / "report.json").read_text())
    assert code == 1 and report["summary"]["rules_run"] == 7
    assert report["pack"]["hash"] == loaded.content_hash
    (pack / "req.ids").write_text("<broken")
    assert main(["check", "--architect", "x.ifc", "--pack", str(pack), "--out", str(out)]) == 2
