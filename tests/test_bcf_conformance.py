"""Phase 4 gate, the part a machine can check: report.bcf from a real run is valid BCF 2.1
and opens in an independent reader with the right topics and elements selected.

The schemas in tests/bcf/ are buildingSMART's, unmodified (see tests/bcf/README.md).
"""

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import ifcopenshell
import pytest

from ludwig import check
from ludwig.model import Severity, Status
from ludwig.report import bcf
from ludwig.rules.packs import load_pack

xmlschema = pytest.importorskip("xmlschema")

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
SCHEMAS = Path(__file__).parent / "bcf"
MODEL = FIX / "ifc" / "duplex_architectural_ifc2x3.ifc"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    pack = load_pack(ROOT / "packs" / "joinery-nl")
    outcome = check.run([MODEL, FIX / "schedule" / "duplex_joinery_schedule_seeded.csv"], pack,
                        FIX / "erp" / "duplex_erp_export_seeded.csv")  # fmt: skip
    out = tmp_path_factory.mktemp("report")
    check.write_reports(out, outcome, pack, markup=False)
    return outcome, out / "report.bcf"


def reported(outcome):
    shown = (Severity.BLOCKER, Severity.WARNING)
    return [f for f in outcome.result.findings if f.status is Status.FAIL and f.severity in shown]


def test_every_file_is_valid_against_the_bcf_2_1_schemas(run):
    _, path = run
    schemas = {"markup.bcf": "markup.xsd", "viewpoint.bcfv": "visinfo.xsd",
               "bcf.version": "version.xsd"}  # fmt: skip
    loaded = {name: xmlschema.XMLSchema(SCHEMAS / xsd) for name, xsd in schemas.items()}
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "bcf.version" in names
        for name in names:
            errors = [e.reason for e in loaded[name.rsplit("/", 1)[-1]].iter_errors(
                zf.read(name).decode())]  # fmt: skip
            assert errors == [], f"{name}: {errors[:3]}"


def test_selected_elements_exist_in_the_model(run):
    outcome, path = run
    model = ifcopenshell.open(str(MODEL))
    with zipfile.ZipFile(path) as zf:
        views = [zf.read(n).decode() for n in zf.namelist() if n.endswith(".bcfv")]
    guids = {g for v in views for g in _attr_values(v, "IfcGuid")}
    assert guids, "no element is selected in any viewpoint"
    for guid in guids:
        assert model.by_guid(guid) is not None


def _attr_values(xml: str, attr: str) -> list[str]:
    from xml.etree import ElementTree as ET

    return [e.get(attr) for e in ET.fromstring(xml).iter() if e.get(attr)]


@pytest.mark.skipif(importlib.util.find_spec("bcf") is None, reason="bcf-client not installed")
def test_an_independent_reader_finds_every_topic(run):
    outcome, path = run
    script = Path(__file__).parent / "bcf" / "read_with_bcf_client.py"
    done = subprocess.run([sys.executable, str(script), str(path)], capture_output=True,
                          text=True, timeout=120, check=True)  # fmt: skip
    topics = {t["guid"]: t for t in json.loads(done.stdout)}
    expected = reported(outcome)
    assert len(topics) == len(expected) == 10
    for finding in expected:
        topic = topics[bcf.topic_guid(finding)]
        assert topic["type"] == ("Error" if finding.severity is Severity.BLOCKER else "Warning")
        assert finding.mark in topic["title"]
    assert any(t["selected"] for t in topics.values())
