"""toolkit — the thin element-API codegen registers against (the new L_*). See BRIEF §5 / [H1].

CRITICAL POLICY [H1]: generated programs target **raw CadQuery** for geometry and use this thin
layer only to *register* semantics — which solids are which Elements, which values are named dims.
We measure raw-vs-wrapped first-pass geometric pass-rate (eval/) before expanding this surface.
Do NOT grow it into a mandatory DSL: that trades away the model's strongest prior (~50% first-pass).
"""
from __future__ import annotations

from geometry.service import GeometryService
from ir.elements import Element, ProgramNode

_geom = GeometryService()


def part(element_id: str, name: str = "", *, node: str | None = None) -> Element:
    """Open a Part element. The program builds geometry with raw CadQuery, then registers
    named dims via `el.register_dim(...)` so the critic and UI sliders can see them."""
    prov = ProgramNode(node_id=node) if node else None
    return Element(id=element_id, type="Part", name=name or element_id, provenance=prov)


def box(element_id: str, length: float, width: float, height: float, *, name: str = "") -> Element:
    """Convenience seed: a dimensioned box Part with its three extents registered as named dims."""
    el = part(element_id, name=name)
    el.geometry = _geom.box(length, width, height)
    el.register_dim("length", length)
    el.register_dim("width", width)
    el.register_dim("height", height)
    return el
