"""BCF 2.1 export: one topic per failed blocker or warning, selecting the IFC elements involved.

BCF is a zip of XML files (buildingSMART BCF-XML 2.1). Topic and viewpoint ids are derived
from the finding, so the same run gives the same ids and a re-run updates, not duplicates.
"""

from __future__ import annotations

import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from ludwig.model import Finding, Severity, SourceKind, Status
from ludwig.report import SEVERITY_ORDER, describe_source
from ludwig.rules.engine import RunResult

_NAMESPACE = uuid.UUID("6f1c2a52-3c1e-4c9b-9a51-1d0a3b7f5e10")
_COLOUR = {Severity.BLOCKER: "FFFF0000", Severity.WARNING: "FFFFA500"}
_TOPIC_TYPE = {Severity.BLOCKER: "Error", Severity.WARNING: "Warning"}
_FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


def topic_guid(f: Finding) -> str:
    """Stable id for a finding: pack, rule and elements."""
    return str(uuid.uuid5(_NAMESPACE, "|".join([f.pack, f.rule_id, *f.element_ids])))


def _xml(root: ET.Element) -> bytes:
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    node = ET.SubElement(parent, tag, attrs)
    if text is not None:
        node.text = text
    return node


def _ifc_guids(f: Finding) -> list[str]:
    out: list[str] = []
    for src in f.evidence:
        if src.kind is SourceKind.IFC and src.ifc_guid and src.ifc_guid not in out:
            out.append(src.ifc_guid)
    return out


def _markup(f: Finding, guid: str, view: str, created: str, ifc_files: list[str]) -> bytes:
    root = ET.Element("Markup")
    if ifc_files:
        header = _sub(root, "Header")
        for name in ifc_files:
            node = _sub(header, "File", isExternal="true")
            _sub(node, "Filename", name)
    topic = _sub(root, "Topic", Guid=guid, TopicType=_TOPIC_TYPE[f.severity], TopicStatus="Open")
    _sub(topic, "Title", f.message or f.rule_id)
    _sub(topic, "Priority", f.severity.value)
    _sub(topic, "Labels", f.rule_id)
    _sub(topic, "Labels", f.pack)
    _sub(topic, "CreationDate", created)
    _sub(topic, "CreationAuthor", "ludwig")
    lines = [f.message, f"Rule: {f.rule_id} ({f.pack} {f.pack_version})"]
    if f.expected is not None:
        lines.append(f"Expected: {f.expected}")
    lines += [f"Source: {describe_source(s)}" for s in f.evidence]
    _sub(topic, "Description", "\n".join(line for line in lines if line))
    viewpoints = _sub(root, "Viewpoints", Guid=view)
    _sub(viewpoints, "Viewpoint", "viewpoint.bcfv")
    return _xml(root)


def _viewpoint(f: Finding, view: str, guids: list[str]) -> bytes:
    root = ET.Element("VisualizationInfo", Guid=view)
    components = _sub(root, "Components")
    if guids:  # the schema allows no empty selection
        selection = _sub(components, "Selection")
        for g in guids:
            _sub(selection, "Component", IfcGuid=g)
    _sub(components, "Visibility", DefaultVisibility="true")
    if guids:
        colour = _sub(_sub(components, "Coloring"), "Color", Color=_COLOUR[f.severity])
        for g in guids:
            _sub(colour, "Component", IfcGuid=g)
    return _xml(root)


def topics(result: RunResult) -> list[Finding]:
    """The findings that become topics: failed blockers and warnings, blockers first."""
    shown = (Severity.BLOCKER, Severity.WARNING)
    chosen = [f for f in result.findings if f.status is Status.FAIL and f.severity in shown]
    return sorted(chosen, key=lambda f: SEVERITY_ORDER[f.severity])


def write(path: str | Path, result: RunResult, created: datetime | None = None) -> Path:
    """Write report.bcf (BCF 2.1)."""
    path = Path(path)
    stamp = (created or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    files: list[tuple[str, bytes]] = []
    version = ET.Element("Version", VersionId="2.1")
    _sub(version, "DetailedVersion", "2.1")
    files.append(("bcf.version", _xml(version)))
    for f in topics(result):
        guid = topic_guid(f)
        view = str(uuid.uuid5(_NAMESPACE, guid + "|viewpoint"))
        ifc_files = sorted({Path(s.file).name for s in f.evidence if s.kind is SourceKind.IFC})
        files.append((f"{guid}/markup.bcf", _markup(f, guid, view, stamp, ifc_files)))
        files.append((f"{guid}/viewpoint.bcfv", _viewpoint(f, view, _ifc_guids(f))))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    return path
