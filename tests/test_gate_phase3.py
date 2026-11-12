"""PLAN phase 3 gate: the invented project delivered as DXF plus PDF schedule gives the same
findings as the IFC version."""

import json
from pathlib import Path

import pytest

from ludwig.cli import main

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
PACK = str(ROOT / "packs" / "joinery-nl")
IFC_SET = [FIX / "ifc" / "duplex_architectural_ifc2x3.ifc",
           FIX / "schedule" / "duplex_joinery_schedule.csv"]  # fmt: skip
DRAWN_SET = [FIX / "dxf" / "duplex_joinery_plan.dxf",
             FIX / "pdf" / "duplex_joinery_schedule.pdf"]  # fmt: skip


def findings(tmp_path, architect, export):
    out = tmp_path / f"{architect[0].suffix[1:]}-{export}"
    erp = str(FIX / "erp" / export)
    code = main(["check", "--architect", *map(str, architect), "--erp", erp,
                 "--pack", PACK, "--out", str(out)])  # fmt: skip
    report = json.loads((out / "report.json").read_text())
    return code, sorted((f["rule_id"], f["mark"] or "", f["status"], f["severity"])
                        for f in report["findings"])  # fmt: skip


@pytest.mark.parametrize("export", ["duplex_erp_export_seeded.csv", "duplex_erp_export.csv"])
def test_drawn_delivery_gives_the_same_findings_as_the_model(tmp_path, export):
    code_ifc, from_model = findings(tmp_path, IFC_SET, export)
    code_2d, from_drawings = findings(tmp_path, DRAWN_SET, export)
    assert code_2d == code_ifc
    assert from_drawings == from_model
    fails = [f for f in from_drawings if f[2] == "fail"]
    assert len(fails) == (10 if "seeded" in export else 0)
