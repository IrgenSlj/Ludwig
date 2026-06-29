"""toolkit — the thin element-API codegen registers against (the new L_*). See BRIEF §5 / [H1].

CRITICAL POLICY [H1]: generated programs target **raw CadQuery** for geometry and use this thin
layer only to *register* semantics — which solids are which Elements, which values are named dims.
We measure raw-vs-wrapped first-pass geometric pass-rate (eval/) before expanding this surface.
Do NOT grow it into a mandatory DSL: that trades away the model's strongest prior (~50% first-pass).

R2 addition: a contextvar-based recorder. When a ``recording()`` context is active, each toolkit
call appends a typed FeatureNode to the yielded FeatureGraph as a side-effect of the existing
geometry path. Default is OFF — zero behavior change when not recording ([H1]).
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Optional

from geometry.service import GeometryService
from ir.elements import Element, ProgramNode, Relation
from ir.feature import FeatureGraph
from toolkit.standards import clearance_hole_mm

_geom = GeometryService()

# ---- feature-graph recorder ------------------------------------------------

_RECORDING: contextvars.ContextVar[Optional[FeatureGraph]] = contextvars.ContextVar(
    "ludwig_recording", default=None
)


@contextmanager
def recording():
    """Turn on feature-graph recording for toolkit calls within this context.

    Yields the active FeatureGraph. Each toolkit call (box/hole/anchor/place/stack/assembly)
    appends a typed FeatureNode as a SIDE EFFECT while recording is active. Recording is
    thread-/task-safe via contextvars — nested or concurrent recordings are independent.

    Example::

        with recording() as g:
            b = box("part", 80, 40, 6)
            clearance_hole(b, "M8", (25, 0))
        # g.nodes == [FeatureNode("box#1",...), FeatureNode("hole#1",...)]
    """
    graph = FeatureGraph()
    token = _RECORDING.set(graph)
    try:
        yield graph
    finally:
        _RECORDING.reset(token)


# ---- toolkit functions -----------------------------------------------------

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
    _g = _RECORDING.get()
    if _g is not None:
        _g.append("box",
                  {"element_id": element_id, "length": length, "width": width, "height": height},
                  [])
        el.graph = _g
    return el


def hole(el: Element, diameter: float, at: tuple[float, float], *,
         name: str | None = None, through: bool = True, depth: float | None = None,
         thread: str | None = None) -> Element:
    """Drill a vertical hole at (x, y), register its diameter, and record it as a feature.

    The (x, y) POSITION is recorded on `el.features` — it is design intent the conventioned
    drawing backend and a future "move the hole" edit both need, and which `register_dim`
    (diameter only) used to discard. Grow the IR from real use (principle #7): the drawing
    engine is the real use that demands the position be first-class, not lost in the kernel.
    """
    el.geometry = _geom.hole(el.geometry, diameter, at, through=through, depth=depth)
    idx = sum(1 for d in el.manifest if d.name.startswith("hole")) + 1
    el.register_dim(name or f"hole_{idx}_dia", diameter)
    el.features.append({
        "kind": "hole", "at": (float(at[0]), float(at[1])), "diameter": float(diameter),
        "through": bool(through), "depth": (None if through else depth), "thread": thread,
    })
    _g = _RECORDING.get()
    if _g is not None:
        _prev = el.graph.result_id if (el.graph is not None and el.graph is _g) else ""
        _params: dict = {
            "diameter": float(diameter),
            "at": (float(at[0]), float(at[1])),
            "through": bool(through),
        }
        if not through:
            _params["depth"] = depth
        if thread is not None:
            _params["thread"] = thread
        _g.append("hole", _params, [_prev] if _prev else [])
        el.graph = _g
    return el


def clearance_hole(el: Element, thread: str, at: tuple[float, float], *, through: bool = True) -> Element:
    """Drill a clearance hole sized from standards.yaml — e.g. 'M8' -> ⌀9.0 (BRIEF §10).
    The thread→diameter mapping is domain knowledge that lives in standards, never in codegen."""
    return hole(el, clearance_hole_mm(thread), at,
                name=f"{thread}_clearance_{_n(el)}", through=through, thread=thread)


def profile(element_id: str, length: float, width: float, height: float, *, name: str = "") -> Element:
    """A member/profile element (beam, rail, trim) extruded along a path. Geometry is a box
    extrusion oriented length along x, width along y, height along z. Type is 'Profile',
    mapping to IfcMember in IFC. Registers length/width/height as named dims."""
    el = part(element_id, name=name)
    el.type = "Profile"
    el.geometry = _geom.box(length, width, height)
    el.register_dim("length", length)
    el.register_dim("width", width)
    el.register_dim("height", height)
    return el


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
    el.features.append({"kind": "anchor", "at": (float(at[0]), float(at[1])),
                        "diameter": float(diameter), "depth": float(depth),
                        "through": False, "thread": None})
    _g = _RECORDING.get()
    if _g is not None:
        _prev = el.graph.result_id if (el.graph is not None and el.graph is _g) else ""
        _g.append("anchor",
                  {"diameter": float(diameter), "at": (float(at[0]), float(at[1])), "depth": float(depth)},
                  [_prev] if _prev else [])
        el.graph = _g
    return el


def place(el: Element, offset: tuple[float, float, float]) -> Element:
    """Move an element's geometry by (dx, dy, dz) mm. Positioning for assemblies — the model says
    `place(top, (0, 0, 10))` instead of hand-rolling a kernel translate. Extents are unchanged, so
    registered dims stay valid. Returns the element for chaining."""
    el.geometry = _geom.translate(el.geometry, offset)
    _g = _RECORDING.get()
    if _g is not None:
        _prev = el.graph.result_id if (el.graph is not None and el.graph is _g) else ""
        _g.append("place", {"offset": [float(c) for c in offset]}, [_prev] if _prev else [])
        el.graph = _g
    return el


def stack(base: Element, top: Element) -> Element:
    """Seat `top` on the +z face of `base` (both built centred on the origin, as box()/panel() are):
    lift `top` by (base_height + top_height)/2 so their faces meet. Returns `top` (now placed).

    Note: geometry is applied directly (not via place()) so that a single 'stack' node appears in
    the feature graph rather than a 'stack' + 'place' pair ([H1] recorder is a side-effect only).
    """
    _, _, bh = _geom.bbox(base.geometry)
    _, _, th = _geom.bbox(top.geometry)
    offset = (0.0, 0.0, (bh + th) / 2.0)
    top.geometry = _geom.translate(top.geometry, offset)
    _g = _RECORDING.get()
    if _g is not None:
        _bi = base.graph.result_id if (base.graph is not None and base.graph is _g) else ""
        _ti = top.graph.result_id if (top.graph is not None and top.graph is _g) else ""
        _inputs = [x for x in [_bi, _ti] if x]
        _g.append("stack", {"offset": [float(c) for c in offset]}, _inputs)
        top.graph = _g
    return top


def assembly(element_id: str, *children: Element, name: str = "") -> Element:
    """Compose several Elements into an Assembly (type 'Assembly') with compound geometry."""
    el = part(element_id, name=name)
    el.type = "Assembly"
    el.children = list(children)
    el.geometry = _geom.compound([c.geometry for c in children if c.geometry is not None])
    for c in children:
        el.relations.append(Relation("contains", c.id))
    _g = _RECORDING.get()
    if _g is not None:
        _child_ids = [c.graph.result_id for c in children
                      if c.graph is not None and c.graph is _g and c.graph.result_id]
        _g.append("assembly", {"element_id": element_id}, _child_ids)
        el.graph = _g
    return el


def _n(el: Element) -> int:
    return sum(1 for d in el.manifest if "clearance" in d.name) + 1
