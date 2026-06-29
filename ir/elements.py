"""The typed semantic element model — the IR, Ludwig's source of truth (BRIEF §3).

Pure Python, zero heavy deps: geometry is a lazy handle so the OCCT/CadQuery kernel
never imports at module load. Grow this from real use, never speculatively (principle #7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from ir.feature import FeatureGraph


@dataclass
class Param:
    """A named, typed, UNIT-CARRYING value. Units are mandatory (BRIEF §10, the #1 silent CAD bug)."""
    name: str
    value: float
    unit: str = "mm"

    def __post_init__(self) -> None:
        if not self.unit:
            raise ValueError(f"Param {self.name!r} has no unit — units are mandatory")


@dataclass
class NamedDim:
    """A named dimension the program registers. Feeds BOTH the dimensional critic and
    the UI's in-place sliders (docs/UX_BRIEF.md). This is the seam the slider binds to."""
    name: str
    value: float
    unit: str = "mm"


@dataclass
class Relation:
    """A typed edge in the element graph."""
    kind: str          # "hosts" | "bounded_by" | "contains" | "references"
    target_id: str


@dataclass
class ProgramNode:
    """A node in the hierarchical program. Provenance resolves a Stage selection to one
    of THESE — never to a raw kernel face/edge id (principle #8 / [H2]: lineage, not handles)."""
    node_id: str
    source_span: Optional[tuple[int, int]] = None   # (start_line, end_line) in the program text
    parent: Optional[str] = None


class BRepHandle:
    """Lazy handle to an OCCT solid. Keeps the heavy kernel out of module import;
    geometry/service.py supplies the builder and materializes on demand."""
    __slots__ = ("_build", "_solid")

    def __init__(self, build: Optional[Callable[[], Any]] = None):
        self._build = build
        self._solid = None

    @property
    def built(self) -> bool:
        return self._solid is not None

    def solid(self) -> Any:
        if self._solid is None:
            if self._build is None:
                raise RuntimeError("BRepHandle has no builder and no cached solid")
            self._solid = self._build()
        return self._solid


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else float(x)


@dataclass
class Element:
    """A typed element owning exact geometry, unit-carrying params, named dims, and relations."""
    id: str
    type: str = "Part"
    name: str = ""
    geometry: Optional[BRepHandle] = None
    params: dict[str, Param] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    manifest: list[NamedDim] = field(default_factory=list)
    # [H3] Through P0/P1 this is ONLY a critic-strictness scalar — it must NOT introduce a
    # second geometry representation into the IR core. Rich loose-geometry behavior is P2–P3.
    crystallization: float = 0.0
    provenance: Optional[ProgramNode] = None
    features: list = field(default_factory=list)
    children: list = field(default_factory=list)
    # R2: feature graph recorded by toolkit/elements.py when recording() context is active.
    # Default None — additive, zero behavior change when recording is off ([H1]).
    graph: Optional[FeatureGraph] = None

    def __post_init__(self) -> None:
        self.crystallization = _clamp01(self.crystallization)

    def register_dim(self, name: str, value: float, unit: str = "mm") -> float:
        """Record a named dimension into the manifest (critic + UI both read it). Returns value
        so codegen can write `w = part.register_dim("width", 80)` inline."""
        self.manifest.append(NamedDim(name, value, unit))
        return value

    def dim(self, name: str) -> Optional[float]:
        for d in self.manifest:
            if d.name == name:
                return d.value
        return None
