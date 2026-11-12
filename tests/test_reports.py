import json
from pathlib import Path

import openpyxl
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
)
from ludwig.report import excel
from ludwig.report import json as json_report
from ludwig.rules import engine
from ludwig.rules.packs import load_pack

DEMO = Path(__file__).resolve().parent / "packs" / "demo"


def _el(eid, etype, side=Side.ERP, **kw):
    return Element(eid, side, etype, [SourceRef("erp.xlsx", SourceKind.ERP, sheet="Orders",
                   cell=f"A{eid[-1]}")], **kw)  # fmt: skip


@pytest.fixture
def run():
    pack = load_pack(DEMO)
    elements = [
        _el("s1", ElementType.WINDOW_SASH, mark="R1", width_mm=1200.0),
        _el("s2", ElementType.WINDOW_SASH, mark="R2", width_mm=1650.0),
        _el("s3", ElementType.WINDOW_SASH, mark="=HYPERLINK(\"x\")", width_mm=None),
        _el("d4", ElementType.DOOR_LEAF, side=Side.ARCHITECT, mark="D1",
            props={"fire_rating_min": 30.0, "sound_reduction_db": 25.0}),
        _el("d5", ElementType.DOOR_LEAF, side=Side.ARCHITECT, mark="D2",
            props={"fire_rating_min": 0.0}),
    ]  # fmt: skip
    warnings = [ParseWarning("model.ifc", "x: 2 values equal the property name; read as not set")]
    return engine.run(elements, pack), pack, warnings


def test_json_report_orders_fail_then_not_checked_and_counts(run, tmp_path):
    result, pack, warnings = run
    path = json_report.write(tmp_path / "r.json", result, pack.name, pack.version, warnings)
    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert [(f["status"], f["severity"], f["mark"]) for f in data["findings"]] == [
        ("fail", "blocker", "R2"),
        ("fail", "warning", "D1"),
        ("not_checked", "blocker", "=HYPERLINK(\"X\")"),
        ("pass", "blocker", "R1"),
        ("not_applicable", "warning", "D2"),
    ]
    assert data["summary"] == {
        "rules_run": 3, "elements_total": 5, "elements_covered": 4, "not_checked": 1,
        "by_status": {"fail": 2, "not_applicable": 1, "not_checked": 1, "pass": 1},
        "fails_by_severity": {"blocker": 1, "warning": 1}, "parse_warnings": 1,
    }  # fmt: skip
    assert data["findings"][0]["evidence"] == [
        {"file": "erp.xlsx", "kind": "erp", "sheet": "Orders", "cell": "A2"}
    ]


def test_json_report_is_byte_identical_across_runs(run, tmp_path):
    result, pack, warnings = run
    a = json_report.write(tmp_path / "a.json", result, pack.name, pack.version, warnings)
    b = json_report.write(tmp_path / "b.json", result, pack.name, pack.version, warnings)
    assert a.read_bytes() == b.read_bytes()


def test_excel_report_rows_sorted_by_severity_with_sources(run, tmp_path):
    result, pack, warnings = run
    path = excel.write(tmp_path / "r.xlsx", result, pack.name, pack.version, warnings)
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Summary", "Findings", "Passed", "Parse warnings"]
    rows = list(wb["Findings"].iter_rows(values_only=True))
    assert rows[0] == excel.COLUMNS
    body = [dict(zip(excel.COLUMNS, r, strict=True)) for r in rows[1:]]
    assert [(r["Severity"], r["Status"], r["Mark"]) for r in body] == [
        ("blocker", "fail", "R2"),
        ("blocker", "not_checked", "=HYPERLINK(\"X\")"),
        ("warning", "fail", "D1"),
    ]
    first = body[0]
    assert first["Production"] == 1650 and first["Drawings"] is None
    assert first["Expected"] == "width_mm <= 1500"
    assert first["Production source"] == "erp.xlsx, sheet Orders, cell A2"
    assert first["Message"] == "Sash R2: width 1650 mm exceeds machine limit 1500 mm"
    assert body[1]["Reason"] == "width_mm is not set"
    assert [r[2] for r in wb["Passed"].iter_rows(min_row=2, values_only=True)] == ["R1"]
    summary = dict(wb["Summary"].iter_rows(min_row=2, values_only=True))
    assert summary["Blockers"] == 1 and summary["Not checked"] == 1
    assert wb["Parse warnings"].max_row == 2


def test_excel_never_writes_customer_text_as_a_formula(run, tmp_path):
    result, pack, warnings = run
    path = excel.write(tmp_path / "r.xlsx", result, pack.name, pack.version, warnings)
    ws = openpyxl.load_workbook(path)["Findings"]
    cells = [c for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    hyperlink = [c for c in cells if c.value.startswith("=")]
    assert hyperlink and all(c.data_type == "s" for c in hyperlink)


def test_empty_run_still_reports_coverage(tmp_path):
    result = engine.run([], load_pack(DEMO))
    data = json_report.to_dict(result, "demo", "0.0.1", [])
    assert data["findings"] == [] and data["summary"]["rules_run"] == 3


def test_compare_findings_show_drawings_and_production_side_by_side(tmp_path):
    from ludwig.match import pairs
    from ludwig.report import by_side

    pack = load_pack(Path(__file__).resolve().parent / "packs" / "reconcile")
    elements = [
        Element("m", Side.ARCHITECT, ElementType.FRAME, [SourceRef("model.ifc", SourceKind.IFC,
                ifc_guid="g1")], mark="K1", width_mm=1200.0, quantity=2),
        Element("s", Side.ARCHITECT, ElementType.FRAME, [SourceRef("architect.csv",
                SourceKind.SHEET, cell="C2")], mark="K1", width_mm=1200.0, quantity=2),
        Element("e", Side.ERP, ElementType.FRAME, [SourceRef("erp.csv", SourceKind.ERP,
                cell="F2")], mark="K1", width_mm=1180.0, quantity=1),
    ]  # fmt: skip
    result = engine.run(elements, pack, pairs(elements))
    path = excel.write(tmp_path / "r.xlsx", result, pack.name, pack.version, [])
    rows = list(openpyxl.load_workbook(path)["Findings"].iter_rows(values_only=True))
    body = {r[3]: dict(zip(excel.COLUMNS, r, strict=True)) for r in rows[1:]}
    width = body["width-matches"]
    assert width["Drawings"] == "model.ifc: 1200, architect.csv: 1200"
    assert width["Production"] == 1180
    assert width["Drawings source"] == "model.ifc, GlobalId g1; architect.csv, cell C2"
    assert width["Production source"] == "erp.csv, cell F2"
    qty = body["quantity-matches"]
    assert (qty["Drawings"], qty["Production"]) == ("model.ifc: 2, architect.csv: 2", 1)
    consistent = Finding("c", "p", "1", Status.FAIL, Severity.WARNING, ["s"],
                         measured={"architect.csv": 2, "model.ifc": 3})  # fmt: skip
    assert by_side(consistent)["values"] == {"architect": {"architect.csv": 2, "model.ifc": 3},
                                            "erp": None}  # fmt: skip
