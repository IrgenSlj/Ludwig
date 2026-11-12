"""The element table and findings (SPEC sections 3 and 7). Every other module speaks these types."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Side(StrEnum):
    ARCHITECT = "architect"
    ERP = "erp"


class ElementType(StrEnum):
    FRAME = "frame"
    WINDOW_SASH = "window_sash"
    DOOR_LEAF = "door_leaf"
    GLAZING = "glazing"
    PANEL = "panel"
    HARDWARE_SET = "hardware_set"


class SourceKind(StrEnum):
    IFC = "ifc"
    SHEET = "sheet"
    DXF = "dxf"
    PDF = "pdf"
    ERP = "erp"


class Status(StrEnum):
    FAIL = "fail"
    PASS = "pass"
    NOT_CHECKED = "not_checked"
    NOT_APPLICABLE = "not_applicable"


class Severity(StrEnum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


# SPEC section 3. Extend only when a rule needs one.
STANDARD_PROPS = frozenset(
    {
        "fire_rating_min",
        "burglary_class",
        "u_value",
        "sound_reduction_db",
        "glazing_type",
        "opening_direction",
        "material",
        "finish",
        "threshold_type",
        "ventilation_grille",
    }
)

ELEMENT_FIELDS = (
    "id",
    "side",
    "type",
    "mark",
    "quantity",
    "width_mm",
    "height_mm",
    "depth_mm",
    "location",
    "parent_id",
)

_LOCATORS = ("ifc_guid", "sheet", "cell", "dxf_handle", "layer", "page", "bbox")


@dataclass(frozen=True)
class SourceRef:
    """Where a value came from: a file plus one locator inside it."""

    file: str
    kind: SourceKind
    ifc_guid: str | None = None
    sheet: str | None = None
    cell: str | None = None
    dxf_handle: str | None = None
    layer: str | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON form; unset locators are left out."""
        d: dict[str, Any] = {"file": self.file, "kind": self.kind.value}
        for name in _LOCATORS:
            value = getattr(self, name)
            if value is not None:
                d[name] = list(value) if name == "bbox" else value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceRef:
        """Inverse of `to_dict`."""
        bbox = d.get("bbox")
        return cls(
            file=d["file"],
            kind=SourceKind(d["kind"]),
            **{k: d.get(k) for k in _LOCATORS if k != "bbox"},
            bbox=tuple(bbox) if bbox is not None else None,
        )


_WHITESPACE = re.compile(r"\s+")


def normalise_mark(raw: object) -> str | None:
    """Trim, upper-case and remove spaces; an empty mark is None."""
    if raw is None:
        return None
    mark = _WHITESPACE.sub("", str(raw)).upper()
    return mark or None


@dataclass
class Element:
    """One row of the element table."""

    id: str
    side: Side
    type: ElementType
    sources: list[SourceRef]
    mark: str | None = None
    quantity: int | None = 1
    width_mm: float | None = None
    height_mm: float | None = None
    depth_mm: float | None = None
    location: str | None = None
    parent_id: str | None = None
    props: dict[str, Any] = field(default_factory=dict)
    # A field whose value came from somewhere other than `sources[0]` records that place here.
    field_sources: dict[str, SourceRef] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError(f"element {self.id}: at least one source is required")
        self.mark = normalise_mark(self.mark)

    def source_of(self, name: str) -> SourceRef:
        """The source of one field: its own if recorded, else the element's first source."""
        return self.field_sources.get(name, self.sources[0])

    def to_dict(self) -> dict[str, Any]:
        """JSON form."""
        return {
            "id": self.id,
            "side": self.side.value,
            "type": self.type.value,
            "mark": self.mark,
            "quantity": self.quantity,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "depth_mm": self.depth_mm,
            "location": self.location,
            "parent_id": self.parent_id,
            "props": dict(sorted(self.props.items())),
            "sources": [s.to_dict() for s in self.sources],
            "field_sources": {k: v.to_dict() for k, v in sorted(self.field_sources.items())},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Element:
        """Inverse of `to_dict`."""
        return cls(
            id=d["id"],
            side=Side(d["side"]),
            type=ElementType(d["type"]),
            mark=d.get("mark"),
            quantity=d.get("quantity", 1),
            width_mm=d.get("width_mm"),
            height_mm=d.get("height_mm"),
            depth_mm=d.get("depth_mm"),
            location=d.get("location"),
            parent_id=d.get("parent_id"),
            props=dict(d.get("props", {})),
            sources=[SourceRef.from_dict(s) for s in d["sources"]],
            field_sources={
                k: SourceRef.from_dict(v) for k, v in d.get("field_sources", {}).items()
            },
        )


@dataclass(frozen=True)
class ParseWarning:
    """Something a parser could not read. Shown in the report, never raised."""

    file: str
    message: str
    source: SourceRef | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON form."""
        d: dict[str, Any] = {"file": self.file, "message": self.message}
        if self.source is not None:
            d["source"] = self.source.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ParseWarning:
        """Inverse of `to_dict`."""
        src = d.get("source")
        return cls(d["file"], d["message"], SourceRef.from_dict(src) if src else None)


@dataclass
class Finding:
    """The result of one rule on one element or pair."""

    rule_id: str
    pack: str
    pack_version: str
    status: Status
    severity: Severity
    element_ids: list[str]
    mark: str | None = None
    measured: Any = None
    expected: Any = None
    message: str = ""
    evidence: list[SourceRef] = field(default_factory=list)
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status is Status.NOT_CHECKED and not self.reason:
            raise ValueError(f"{self.rule_id}: a not_checked finding needs a reason")

    def to_dict(self) -> dict[str, Any]:
        """JSON form."""
        return {
            "rule_id": self.rule_id,
            "pack": self.pack,
            "pack_version": self.pack_version,
            "status": self.status.value,
            "severity": self.severity.value,
            "element_ids": list(self.element_ids),
            "mark": self.mark,
            "measured": self.measured,
            "expected": self.expected,
            "message": self.message,
            "evidence": [s.to_dict() for s in self.evidence],
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Finding:
        """Inverse of `to_dict`."""
        return cls(
            rule_id=d["rule_id"],
            pack=d["pack"],
            pack_version=d["pack_version"],
            status=Status(d["status"]),
            severity=Severity(d["severity"]),
            element_ids=list(d["element_ids"]),
            mark=d.get("mark"),
            measured=d.get("measured"),
            expected=d.get("expected"),
            message=d.get("message", ""),
            evidence=[SourceRef.from_dict(s) for s in d.get("evidence", [])],
            reason=d.get("reason"),
        )


class MatchStatus(StrEnum):
    MATCHED = "matched"
    MISSING_IN_ERP = "missing_in_erp"
    NOT_IN_ARCHITECT_SET = "not_in_architect_set"
    AMBIGUOUS = "ambiguous"


@dataclass
class Match:
    """Architect elements paired with ERP elements (SPEC section 5); one side may be empty."""

    status: MatchStatus
    type: ElementType
    mark: str | None
    architect: list[Element]
    erp: list[Element]
    by: str | None = None  # "mark" or "fallback" when matched

    @property
    def elements(self) -> list[Element]:
        """Both sides, architect first."""
        return [*self.architect, *self.erp]
