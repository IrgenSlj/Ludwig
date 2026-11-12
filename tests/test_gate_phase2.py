"""PLAN phase 2 gate: an invented project with ten seeded mismatches, all found end to end."""

import json
from pathlib import Path

from ludwig.cli import EXIT_BLOCKERS, EXIT_OK, main

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
ARCHITECT = [str(FIX / "ifc" / "duplex_architectural_ifc2x3.ifc"),
             str(FIX / "schedule" / "duplex_joinery_schedule.csv")]  # fmt: skip
PACK = str(ROOT / "packs" / "joinery-nl")

SEEDED = [
    ("erp-glazing-type", "01"),  # HR++ ordered as Triple
    ("erp-quantity", "02"),  # 8 drawn, 6 ordered
    ("erp-height", "03"),  # 759 typed as 795
    ("erp-width", "05"),  # 4835 ordered as 4855
    ("erp-opening-direction", "28"),  # left-hand pair ordered right-hand
    ("erp-opening-direction", "32"),  # left/right counts swapped, total unchanged
    ("erp-fire-rating", "33"),  # 30 min door ordered without a rating
    ("erp-width", "36"),  # 1172.5 typed as 1127.5
    ("missing-in-erp", "56"),  # position never entered
    ("not-in-architect-set", "99"),  # position not in the drawings
]


def check(tmp_path, export):
    out = tmp_path / export
    code = main(["check", "--architect", *ARCHITECT, "--erp", str(FIX / "erp" / export),
                 "--pack", PACK, "--out", str(out)])  # fmt: skip
    return code, json.loads((out / "report.json").read_text())


def test_all_ten_seeded_mismatches_are_found_and_nothing_else(tmp_path):
    code, report = check(tmp_path, "duplex_erp_export_seeded.csv")
    assert code == EXIT_BLOCKERS
    found = sorted((f["rule_id"], f["mark"]) for f in report["findings"]
                   if f["status"] in ("fail", "not_checked"))  # fmt: skip
    assert found == sorted(SEEDED)
    for f in report["findings"]:
        if f["status"] == "fail":
            assert f["evidence"] and f["message"]
            assert (
                any(e["kind"] == "erp" for e in f["evidence"]) or f["rule_id"] == "missing-in-erp"
            )


def test_clean_export_gives_no_findings(tmp_path):
    code, report = check(tmp_path, "duplex_erp_export.csv")
    assert code == EXIT_OK
    assert report["summary"]["by_status"].get("fail", 0) == 0
    assert report["summary"]["not_checked"] == 0


def test_grouped_model_elements_cite_every_occurrence(tmp_path):
    _, report = check(tmp_path, "duplex_erp_export_seeded.csv")
    [door28] = [f for f in report["findings"]
                if f["rule_id"] == "erp-opening-direction" and f["mark"] == "28"]  # fmt: skip
    guids = [e["ifc_guid"] for e in door28["evidence"] if e["kind"] == "ifc"]
    assert len(guids) == len(set(guids)) == 4
