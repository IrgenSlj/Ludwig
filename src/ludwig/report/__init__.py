"""Reporters: each writes findings to one format. They sort and format, never recompute."""

from __future__ import annotations

from typing import Any

from ludwig.model import ELEMENT_FIELDS, Finding, Severity, SourceKind, SourceRef, Status

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


_UNMATCHED_KEYS = {"architect set": "architect", "production data": "erp"}


def _side_key(key: Any) -> str | None:
    """'architect' or 'erp' for a compare path or an unmatched count key, else None."""
    if key in _UNMATCHED_KEYS:
        return _UNMATCHED_KEYS[key]
    side, _, name = str(key).partition(".")
    if side in ("architect", "erp") and (name in ELEMENT_FIELDS or name.startswith("props.")):
        return side
    return None


def by_side(f: Finding) -> dict[str, Any]:
    """The measured value and the evidence split into drawings (architect) and production (erp).

    A compare or unmatched finding names both sides in `measured`; any other finding's value
    belongs to the side its evidence comes from.
    """
    sources = {"architect": [s for s in f.evidence if s.kind is not SourceKind.ERP],
               "erp": [s for s in f.evidence if s.kind is SourceKind.ERP]}  # fmt: skip
    values: dict[str, Any] = {"architect": None, "erp": None}
    measured = f.measured
    if isinstance(measured, dict) and measured and all(_side_key(k) for k in measured):
        for key, value in measured.items():
            values[_side_key(key)] = value
    elif sources["erp"] and not sources["architect"]:
        values["erp"] = measured
    else:
        values["architect"] = measured
    return {"values": values, "sources": sources}
