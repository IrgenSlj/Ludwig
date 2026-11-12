import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from ludwig.model import Finding, Severity, SourceKind, SourceRef, Status
from ludwig.report import bcf
from ludwig.rules.engine import RunResult

WHEN = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)


def finding(rule, severity, status=Status.FAIL, guids=(), message="Frame K1: <width> & more"):
    evidence = [SourceRef("model.ifc", SourceKind.IFC, ifc_guid=g) for g in guids]
    evidence.append(SourceRef("erp.csv", SourceKind.ERP, cell="F2"))
    return Finding(rule, "joinery-nl", "0.1.0", status, severity, [f"{rule}-a", f"{rule}-b"],
                   mark="K1", message=message, expected="architect.width_mm == erp.width_mm",
                   evidence=evidence,
                   reason="x" if status is Status.NOT_CHECKED else None)  # fmt: skip


@pytest.fixture
def result():
    return RunResult([
        finding("w", Severity.WARNING, guids=("2O2Fr$t4X7Zf8NOew3FLOH",)),
        finding("b", Severity.BLOCKER, guids=("1aj$VJZFn2TxepZUBcKp$i", "1hOSvn6df7F8_7GcBWlS8Z")),
        finding("i", Severity.INFO),
        finding("p", Severity.BLOCKER, status=Status.PASS),
        finding("n", Severity.BLOCKER, status=Status.NOT_CHECKED),
        finding("e", Severity.WARNING),
    ], rules_run=6, elements_total=2, elements_covered=2)  # fmt: skip


def read(path):
    with zipfile.ZipFile(path) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def test_one_topic_per_failed_blocker_or_warning(result, tmp_path):
    files = read(bcf.write(tmp_path / "r.bcf", result, WHEN))
    assert ET.fromstring(files["bcf.version"]).get("VersionId") == "2.1"
    topics = [ET.fromstring(files[n]) for n in sorted(files) if n.endswith("markup.bcf")]
    assert sorted(t.find("Topic/Labels").text for t in topics) == ["b", "e", "w"]
    assert len([n for n in files if n.endswith("viewpoint.bcfv")]) == 3


def test_topic_selects_and_colours_the_ifc_elements(result, tmp_path):
    files = read(bcf.write(tmp_path / "r.bcf", result, WHEN))
    blocker = next(f for f in result.findings if f.rule_id == "b")
    guid = bcf.topic_guid(blocker)
    markup = ET.fromstring(files[f"{guid}/markup.bcf"])
    topic = markup.find("Topic")
    assert (topic.get("Guid"), topic.get("TopicType"), topic.get("TopicStatus")) == (
        guid, "Error", "Open")  # fmt: skip
    assert topic.find("Title").text == "Frame K1: <width> & more"
    assert topic.find("CreationDate").text == "2026-11-12T09:30:00Z"
    assert "Source: erp.csv, cell F2" in topic.find("Description").text
    assert markup.find("Header/File").get("isExternal") == "true"
    assert markup.find("Header/File/Filename").text == "model.ifc"
    view = ET.fromstring(files[f"{guid}/viewpoint.bcfv"])
    assert view.get("Guid") == markup.find("Viewpoints").get("Guid")
    selected = [c.get("IfcGuid") for c in view.findall("Components/Selection/Component")]
    assert selected == ["1aj$VJZFn2TxepZUBcKp$i", "1hOSvn6df7F8_7GcBWlS8Z"]
    assert view.find("Components/Coloring/Color").get("Color") == "FFFF0000"


def test_finding_without_model_elements_has_no_empty_selection(result, tmp_path):
    files = read(bcf.write(tmp_path / "r.bcf", result, WHEN))
    plain = next(f for f in result.findings if f.rule_id == "e")
    view = ET.fromstring(files[f"{bcf.topic_guid(plain)}/viewpoint.bcfv"])
    assert view.find("Components/Selection") is None
    assert view.find("Components/Visibility") is not None


def test_same_run_gives_same_bytes_and_ids(result, tmp_path):
    a = Path(bcf.write(tmp_path / "a.bcf", result, WHEN)).read_bytes()
    b = Path(bcf.write(tmp_path / "b.bcf", result, WHEN)).read_bytes()
    assert a == b
