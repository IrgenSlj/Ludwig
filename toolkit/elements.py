"""toolkit — the thin element-API codegen registers against (the new L_*). See BRIEF §5 / [H1].

CRITICAL POLICY [H1]: generated programs target **raw CadQuery** for geometry and use this thin
layer only to *register* semantics — which solids are which Elements, which values are named dims.
We measure raw-vs-wrapped first-pass geometric pass-rate (eval/) before expanding this surface.
Do NOT grow it into a mandatory DSL: that trades away the model's strongest prior (~50% first-pass).
"""
from __future__ import annotations

from geometry.service import GeometryService
from ir.elements import Element, ProgramNode
from toolkit.standards import clearance_hole_mm

_geom = GeometryService()


def part(element_id: str, name: str = "", *, node: str | None = None) -> Element:
    """Open a Part element. The program builds geometry with raw CadQuery, then registers
    named dims via `el.register_dim(...)` so the critic and UI sliders can see them."""
    prov = ProgramNode(node_id=node) if node else None
    return Element(id=element_id, type="Part", name=name or element_id, provenance=prov)


def box(element_id: str, length: float, width: float, height: float, *, name: str = "") -> Element:
    """A dimensioned box Part with its three extents registered as named dims."""
    el = part(element_id, name=name)
    el.geometry = _geom.box(length, width, height)
    el.register_dim("length", length)
    el.register_dim("width", width)
    el.register_dim("height", height)
    return el


def hole(el: Element, diameter: float, at: tuple[float, float], *,
         name: str | None = None, through: bool = True) -> Element:
    """Drill a vertical hole at (x, y) and register its diameter as a named dim."""
    el.geometry = _geom.hole(el.geometry, diameter, at, through=through)
    idx = sum(1 for d in el.manifest if d.name.startswith("hole")) + 1
    el.register_dim(name or f"hole_{idx}_dia", diameter)
    return el


def clearance_hole(el: Element, thread: str, at: tuple[float, float], *, through: bool = True) -> Element:
    """Drill a clearance hole sized from standards.yaml — e.g. 'M8' -> ⌀9.0 (BRIEF §10).
    The thread→diameter mapping is domain knowledge that lives in standards, never in codegen."""
    return hole(el, clearance_hole_mm(thread), at, name=f"{thread}_clearance_{_n(el)}", through=through)


def panel(element_id: str, length: float, height: float, thickness: float, *, name: str = "") -> Element:
    """A precast wall panel (P1) — a Part of type 'Panel'. Oriented x=length, y=thickness, z=height,
    so the large faces are the length×height elevation. Registers length/thickness/height as named dims."""
    el = part(element_id, name=name)
    el.type = "Panel"
    el.geometry = _geom.box(length, thickness, height)
    el.register_dim("length", length)
    el.register_dim("thickness", thickness)
    el.register_dim("height", height)
    return el


def anchor(el: Element, diameter: float, at: tuple[float, float], depth: float, *, name: str | None = None) -> Element:
    """A cast-in anchor pocket — a blind hole drilled `depth` mm into the top (+z) edge at (x, y)."""
    el.geometry = _geom.hole(el.geometry, diameter, at, through=False, depth=depth)
    idx = sum(1 for d in el.manifest if d.name.startswith("anchor")) + 1
    el.register_dim(name or f"anchor_{idx}_dia", diameter)
    return el


def _n(el: Element) -> int:
    return sum(1 for d in el.manifest if "clearance" in d.name) + 1
