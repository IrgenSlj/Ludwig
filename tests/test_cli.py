import json
import shutil
from pathlib import Path

import pytest

from ludwig.cli import EXIT_BLOCKERS, EXIT_OK, EXIT_USAGE, main

ROOT = Path(__file__).resolve().parent.parent
DUPLEX = ROOT / "fixtures" / "ifc" / "duplex_architectural_ifc2x3.ifc"
SCHEDULE = ROOT / "fixtures" / "schedule" / "duplex_joinery_schedule.csv"
ERP = ROOT / "fixtures" / "erp" / "duplex_erp_export.csv"


def make_pack(tmp_path: Path, max_width: int) -> Path:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack.yaml").write_text("name: t\nversion: '1'\n")
    (pack / "limits.yaml").write_text(f"frame:\n  max_width_mm: {max_width}\n")
    (pack / "checks.yaml").write_text(
        "- id: frame-width-max\n  kind: require\n  applies_to: {type: frame}\n"
        "  require: width_mm <= limits.frame.max_width_mm\n  severity: blocker\n"
        "  message: \"Frame {mark}: {width_mm} mm over {limits.frame.max_width_mm} mm\"\n"
    )
    return pack


def run(tmp_path, *args):
    return main(["check", *args, "--out", str(tmp_path / "out")])


def test_blockers_give_exit_1_and_both_reports(tmp_path, capsys):
    code = run(tmp_path, "--architect", str(DUPLEX), "--pack", str(make_pack(tmp_path, 4000)))
    assert code == EXIT_BLOCKERS
    data = json.loads((tmp_path / "out" / "report.json").read_text())
    fails = [f["mark"] for f in data["findings"] if f["status"] == "fail"]
    assert fails == ["05"]  # the 4835 mm window
    assert (tmp_path / "out" / "report.xlsx").exists()
    assert "1 blockers" in capsys.readouterr().out


def test_no_blockers_gives_exit_0(tmp_path):
    pack = make_pack(tmp_path, 5000)
    assert run(tmp_path, "--architect", str(DUPLEX), str(SCHEDULE), "--pack", str(pack)) == EXIT_OK
    data = json.loads((tmp_path / "out" / "report.json").read_text())
    assert data["summary"]["elements_total"] == 12 + 12  # IFC groups + schedule rows


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["check"],
        ["check", "--architect", "x.ifc", "--pack", "p"],  # no --out
        ["frobnicate"],
    ],
)
def test_argument_errors_give_exit_2(argv):
    with pytest.raises(SystemExit) as info:
        main(argv)
    assert info.value.code == EXIT_USAGE


def test_missing_file_unknown_type_bad_pack_and_erp_give_exit_2(tmp_path, capsys):
    pack = make_pack(tmp_path, 4000)
    assert run(tmp_path, "--architect", "nope.ifc", "--pack", str(pack)) == EXIT_USAGE
    dwg = tmp_path / "plan.dwg"
    dwg.write_text("x")
    assert run(tmp_path, "--architect", str(dwg), "--pack", str(pack)) == EXIT_USAGE
    assert run(tmp_path, "--architect", str(DUPLEX), "--pack", str(tmp_path)) == EXIT_USAGE
    erp = ["--erp", str(ERP), "--mapping", "m.yaml"]
    assert run(tmp_path, "--architect", str(DUPLEX), *erp, "--pack", str(pack)) == EXIT_USAGE
    assert run(tmp_path, "--architect", str(DUPLEX), "--mapping", "m.yaml",
               "--pack", str(pack)) == EXIT_USAGE  # fmt: skip
    err = capsys.readouterr().err
    assert "file not found" in err and "unsupported file type .dwg" in err
    assert "m.yaml: file not found" in err and "--mapping needs --erp" in err


def test_erp_export_is_read_with_its_mapping(tmp_path):
    pack = make_pack(tmp_path, 5000)
    assert run(tmp_path, "--architect", str(DUPLEX), "--erp", str(ERP), "--pack", str(pack)) == 0
    data = json.loads((tmp_path / "out" / "report.json").read_text())
    assert data["summary"]["elements_total"] == 12 + 12  # IFC groups + ERP frame lines


def test_schedule_without_mapping_gives_exit_2(tmp_path, capsys):
    lonely = tmp_path / "schedule.csv"
    shutil.copy(SCHEDULE, lonely)
    pack = make_pack(tmp_path, 4000)
    assert run(tmp_path, "--architect", str(lonely), "--pack", str(pack)) == EXIT_USAGE
    assert "schedule.mapping.yaml" in capsys.readouterr().err


def test_unreadable_ifc_is_a_parse_warning_not_a_crash(tmp_path):
    bad = tmp_path / "bad.ifc"
    bad.write_text("garbage")
    assert run(tmp_path, "--architect", str(bad), "--pack", str(make_pack(tmp_path, 1))) == EXIT_OK
    data = json.loads((tmp_path / "out" / "report.json").read_text())
    assert data["summary"]["parse_warnings"] == 1


def test_dxf_drawing_is_read_with_the_default_mapping(tmp_path):
    plan = ROOT / "fixtures" / "dxf" / "duplex_joinery_plan.dxf"
    pack = make_pack(tmp_path, 4000)
    assert run(tmp_path, "--architect", str(plan), "--pack", str(pack)) == EXIT_BLOCKERS
    data = json.loads((tmp_path / "out" / "report.json").read_text())
    [fail] = [f for f in data["findings"] if f["status"] == "fail"]
    assert fail["mark"] == "05" and fail["evidence"][0]["kind"] == "dxf"
