"""Reporters: each writes findings to one format. They sort and format, never recompute."""

from __future__ import annotations

from ludwig.model import Finding, Severity, SourceRef, Status

STATUS_ORDER = {Status.FAIL: 0, Status.NOT_CHECKED: 1, Status.PASS: 2, Status.NOT_APPLICABLE: 3}
SEVERITY_ORDER = {Severity.BLOCKER: 0, Severity.WARNING: 1, Severity.INFO: 2}


def report_order(findings: list[Finding]) -> list[Finding]:
    """Fail first, then not_checked, then the rest; blockers first within each; stable."""
    return sorted(findings, key=lambda f: (STATUS_ORDER[f.status], SEVERITY_ORDER[f.severity]))


def describe_source(src: SourceRef) -> str:
    """One source as a short human-readable reference."""
    parts = [src.file]
    if src.ifc_guid:
        parts.append(f"GlobalId {src.ifc_guid}")
    if src.sheet:
        parts.append(f"sheet {src.sheet}")
    if src.cell:
        parts.append(f"cell {src.cell}")
    if src.dxf_handle:
        parts.append(f"handle {src.dxf_handle}")
    if src.layer:
        parts.append(f"layer {src.layer}")
    if src.page is not None:
        parts.append(f"page {src.page}")
    if src.bbox:
        parts.append("box " + ",".join(f"{v:g}" for v in src.bbox))
    return ", ".join(parts)
