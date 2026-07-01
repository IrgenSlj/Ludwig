"""Section-drawing backend — the cut sheet (R30, SECTIONS track; the moat's second sheet).

A section shows what a plan/elevation cannot: the material a cutting plane passes through. Ludwig
slices the exact B-rep (R29's `section` primitive), poché-hatches the cut material with a HEAVY cut
boundary, and draws the silhouette BEYOND the cut thin — the conventioned reading a fabricator or
erector expects. Same house style as the shop drawing (standards.yaml: drawing): the scale ladder,
true-mm dimensions via DIMLFAC, the title block. It reuses the shop-drawing view model (`_View`/`_uv`)
so the two sheets are visibly one family.

Where does the plane come from? A declared section on the IR (R33's `toolkit.section` records
{kind:'section', axis, offset}) if present; otherwise the default centroidal LONGITUDINAL plane — cut
perpendicular to the SHORTEST extent, through the centroid — the broadest, most informative section
(for a plate that is the through-thickness cut that reveals the holes as voids).

Robust by construction: every loop / edge / dim / hatch is best-effort and isolated, so an OCCT or
ezdxf hiccup degrades a detail, never the sheet. Self-registering — added by import, no loop change ([H4]).
"""
from __future__ import annotations

from pathlib import Path

from backends.shopdrawing import (
    _View,
    _bbox,
    _conf,
    _dimstyle,
    _frame_and_titleblock,
    _hdim,
    _render_preview,
    _scale_label,
    _straight_edges,
    _vdim,
)

name = "section"
fmt = "dxf"
fabrication = False   # a section is a derived view, not a gated fabrication file

_AXIS_UV = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}   # cut ⟂ axis → in-plane (u, v) model axes
_AXIS_VIEW = {"x": "RIGHT", "y": "FRONT", "z": "TOP"}  # the shop-drawing view looking along the cut axis
_AXIS_LABEL = {"x": "YZ PLANE", "y": "XZ PLANE", "z": "XY PLANE"}  # a cut ⟂ axis lies in the other two
_MARGIN_MM = 24.0     # paper margin reserved around the section view for dimensions


# --------------------------------------------------------------------------- #
# backend entry point
# --------------------------------------------------------------------------- #

def compile(ir, out_dir) -> Path:  # noqa: A001 - matches the Backend protocol
    """Author a poché-hatched, dimensioned, title-blocked section DXF; return its path.
    Writes a best-effort PNG preview alongside it (the moat, made visible)."""
    if ir.geometry is None:
        raise ValueError(f"element {ir.id!r} has no geometry to section")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ir.id}_section.dxf"

    axis, offset = _section_spec(ir)
    doc = _build_section_sheet(ir, axis, offset)
    doc.saveas(str(path))
    _render_preview(path, doc)
    return path


def _section_spec(ir) -> tuple[str, float]:
    """The declared section plane if the IR carries one (R33's toolkit.section records
    {kind:'section', axis, offset}); else — or for any field left unspecified — the centroidal
    longitudinal default. Uses the SAME resolver as the live cut so drawing and slice agree."""
    from geometry import GeometryService

    g = GeometryService()
    for f in getattr(ir, "features", []):
        if isinstance(f, dict) and f.get("kind") == "section":
            axis, offset = f.get("axis"), f.get("offset")
            if axis is None or offset is None:
                axis, offset = g.default_section_plane(ir.geometry, axis=axis)
            return str(axis), float(offset)
    return g.default_section_plane(ir.geometry)


# --------------------------------------------------------------------------- #
# cut geometry (discretized so hole rims render as true circular voids)
# --------------------------------------------------------------------------- #

def _edge_pts(edge, u_ax: int, v_ax: int) -> list[tuple[float, float]]:
    """Sample one edge to (u, v): a LINE gives its two endpoints (exact corners), a curve is
    discretized. `section_profile` returns only raw wire vertices, which collapse a circle to a
    single point — sampling the edge is what makes poché voids and cut boundaries true curves."""
    try:
        n = 1 if edge.geomType() == "LINE" else 24
    except Exception:
        n = 24
    out = []
    for p in edge.positions([k / n for k in range(n + 1)]):
        t = p.toTuple()
        out.append((t[u_ax], t[v_ax]))
    return out


def _ordered_loop(wire, u_ax: int, v_ax: int) -> list[tuple[float, float]]:
    """A wire's vertices in connectivity order (exact corners preserved), by walking the edge chain —
    OCCT does not guarantee `Wire.Edges()` is head-to-tail, so we stitch by matching endpoints."""
    def near(a, b) -> bool:
        return abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6

    segs = [_edge_pts(e, u_ax, v_ax) for e in wire.Edges()]
    segs = [s for s in segs if len(s) >= 2]
    if not segs:
        return []
    chain = list(segs.pop(0))
    while segs:
        tail = chain[-1]
        for i, s in enumerate(segs):
            if near(s[0], tail):
                chain += s[1:]; segs.pop(i); break
            if near(s[-1], tail):
                chain += list(reversed(s))[1:]; segs.pop(i); break
        else:
            chain += segs.pop(0)          # disconnected — append best-effort, never loop forever
    out = [chain[0]]
    for p in chain[1:]:
        if not near(p, out[-1]):
            out.append(p)
    return out


def _cut_faces(handle, axis: str, offset: float):
    """The cut face(s) lying ON the plane, each as {'outer': loop, 'inners': [loop,…]} in (u, v),
    plus the kept half-solid (for the beyond silhouette). A through-feature yields several outer
    faces; an enclosed void yields inner loops. Returns ([], kept) if nothing lies on the plane."""
    from geometry import GeometryService

    g = GeometryService()
    kept = g.section(handle, axis=axis, offset=offset, keep="+")
    solid = kept.solid()
    ai = {"x": 0, "y": 1, "z": 2}[axis]
    u_ax, v_ax = _AXIS_UV[axis]
    faces = []
    for f in solid.faces().vals():
        try:
            c = f.Center().toTuple()
            n = f.normalAt().toTuple()
        except Exception:
            continue
        if abs(c[ai] - offset) < 1e-4 and abs(abs(n[ai]) - 1) < 1e-3:
            outer = _ordered_loop(f.outerWire(), u_ax, v_ax)
            inners = [lp for lp in (_ordered_loop(w, u_ax, v_ax) for w in f.innerWires()) if len(lp) >= 3]
            if len(outer) >= 3:
                faces.append({"outer": outer, "inners": inners})
    return faces, kept


# --------------------------------------------------------------------------- #
# sheet
# --------------------------------------------------------------------------- #

def _build_section_sheet(ir, axis: str, offset: float):
    import ezdxf

    cfg = _conf()
    sheet, txt, lw, tb = cfg["sheet"], cfg["text"], cfg["line_weights_mm"], cfg["title_block"]
    sw, sh, margin = float(sheet["width_mm"]), float(sheet["height_mm"]), float(sheet["margin_mm"])
    tb_h = float(tb["height_mm"])

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LUNITS"] = 2
    msp = doc.modelspace()
    _section_layers(doc, lw)

    xmin, xmax, ymin, ymax, zmin, zmax = _bbox(ir.geometry)
    L, W, H = xmax - xmin, ymax - ymin, zmax - zmin
    ranges = {"x": (xmin, xmax), "y": (ymin, ymax), "z": (zmin, zmax)}
    ua, va = _AXIS_UV[axis]
    umin, umax = ranges[("x", "y", "z")[ua]]
    vmin, vmax = ranges[("x", "y", "z")[va]]
    du, dv = umax - umin, vmax - vmin

    denom = _fit_scale(cfg, du, dv, sw, sh, margin, tb_h)
    s = 1.0 / denom
    ox, oy = _place(du, dv, s, sw, sh, margin, tb_h)
    view = _View(_AXIS_VIEW[axis], "SECTION", ox, oy, umin, vmin, s)

    faces, kept = _cut_faces(ir.geometry, axis, offset)
    _draw_beyond(msp, view, kept, axis, offset)     # thin silhouette behind the cut (drawn first, under)
    for face in faces:                              # poché + heavy cut boundary on top
        _draw_poche(msp, view, face)
    for face in faces:
        _draw_cut_boundary(msp, view, face)

    _dimstyle(doc, txt, denom)
    _dimension(msp, view, umin, umax, vmin, vmax)
    _section_title(msp, view, du * s, axis, offset, denom, txt)
    _frame_and_titleblock(msp, ir, cfg, denom, L, W, H, sw, sh, margin, tb, txt)
    return doc


def _section_layers(doc, lw) -> None:
    import ezdxf

    mm = lambda key, d: int(round(float(lw.get(key, d)) * 100))  # noqa: E731 - ezdxf lineweight is 1/100 mm
    spec = [
        ("CUT",       ezdxf.colors.WHITE,  "CONTINUOUS", mm("cut", 0.50)),      # heavy cut boundary
        ("POCHE",     ezdxf.colors.GRAY,   "CONTINUOUS", mm("poche", 0.13)),    # hatched cut material
        ("BEYOND",    ezdxf.colors.GRAY,   "CONTINUOUS", mm("hidden", 0.18)),   # thin, behind the cut
        ("DIMENSION", ezdxf.colors.YELLOW, "CONTINUOUS", mm("dimension", 0.13)),
        ("TEXT",      ezdxf.colors.GREEN,  "CONTINUOUS", mm("dimension", 0.13)),
        ("BORDER",    ezdxf.colors.WHITE,  "CONTINUOUS", mm("border", 0.50)),
    ]
    for lname, color, ltype, weight in spec:
        doc.layers.add(lname, color=color, linetype=ltype, lineweight=weight)


def _draw_poche(msp, view, face) -> None:
    """Shade the cut material: a solid light-grey fill bounded by the face's outer loop, with its inner
    loops (holes/voids) punched out as islands. Solid poché is the robust convention — it renders in
    every DXF viewer and the raster preview alike, and the white voids read the holes instantly.
    A diagonal ANSI31 pattern is the fallback if solid fill is unavailable."""
    outer = [view.p(u, v) for (u, v) in face["outer"]]
    if len(outer) < 3:
        return
    inners = [[view.p(u, v) for (u, v) in lp] for lp in face["inners"] if len(lp) >= 3]
    try:
        import ezdxf

        hatch = msp.add_hatch(color=9, dxfattribs={"layer": "POCHE"})   # ACI 9 = light grey
        hatch.set_solid_fill(color=9)
        hatch.paths.add_polyline_path(outer, is_closed=True, flags=ezdxf.const.BOUNDARY_PATH_EXTERNAL)
        for lp in inners:
            hatch.paths.add_polyline_path(lp, is_closed=True, flags=ezdxf.const.BOUNDARY_PATH_DEFAULT)
        hatch.dxf.hatch_style = 0     # nested island detection → inner loops punch voids
    except Exception:
        try:
            h2 = msp.add_hatch(dxfattribs={"layer": "POCHE"})
            h2.set_pattern_fill("ANSI31", scale=3.0)
            h2.paths.add_polyline_path(outer, is_closed=True)
        except Exception:
            pass


def _draw_cut_boundary(msp, view, face) -> None:
    """Heavy boundary on the cut edges — outer loop and every void."""
    for loop in [face["outer"], *face["inners"]]:
        pts = [view.p(u, v) for (u, v) in loop]
        if len(pts) >= 2:
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "CUT"})


def _draw_beyond(msp, view, kept, axis: str, offset: float) -> None:
    """Thin silhouette of the material beyond the cut — the kept solid's straight edges, dropping any
    that lie ON the cutting plane (those are the cut boundary, drawn heavy)."""
    ai = {"x": 0, "y": 1, "z": 2}[axis]
    for a, b in _straight_edges(kept):
        if abs(a[ai] - offset) < 1e-6 and abs(b[ai] - offset) < 1e-6:
            continue
        ua, va = _uv(view.key, *a)
        ub, vb = _uv(view.key, *b)
        p0, p1 = view.p(ua, va), view.p(ub, vb)
        if abs(p0[0] - p1[0]) < 1e-9 and abs(p0[1] - p1[1]) < 1e-9:
            continue
        msp.add_line(p0, p1, dxfattribs={"layer": "BEYOND"})


# --------------------------------------------------------------------------- #
# scale / layout / dims / title  (single-view variants of the shop-drawing helpers)
# --------------------------------------------------------------------------- #

def _fit_scale(cfg, du, dv, sw, sh, margin, tb_h) -> float:
    """Largest scale on the ladder that fits the single section view in the drawing area."""
    avail_w = sw - 2 * margin - 2 * _MARGIN_MM
    avail_h = sh - 2 * margin - tb_h - 2 * _MARGIN_MM
    ladder = [float(d) for d in cfg["scale_ladder"]] or [1.0]
    fitting = [(max((du / d) / avail_w, (dv / d) / avail_h), d) for d in ladder
               if max((du / d) / avail_w, (dv / d) / avail_h) <= 1.0]
    return max(fitting)[1] if fitting else max(ladder)


def _place(du, dv, s, sw, sh, margin, tb_h) -> tuple[float, float]:
    """Lower-left paper corner that centres the view in the area above the title block."""
    ax0, ax1 = margin + _MARGIN_MM, sw - margin - _MARGIN_MM
    ay0, ay1 = margin + tb_h + _MARGIN_MM, sh - margin - _MARGIN_MM
    return (ax0 + max(0.0, (ax1 - ax0 - du * s) / 2), ay0 + max(0.0, (ay1 - ay0 - dv * s) / 2))


def _dimension(msp, view, umin, umax, vmin, vmax) -> None:
    off = _MARGIN_MM * 0.55
    try:
        _hdim(msp, view.px(umin), view.px(umax), view.oy, view.oy - off)
        _vdim(msp, view.py(vmin), view.py(vmax), view.ox, view.ox - off)
    except Exception:
        pass


def _section_title(msp, view, paper_w, axis, offset, denom, txt) -> None:
    from ezdxf.enums import TextEntityAlignment

    h = float(txt["title_height_mm"])
    label = f"SECTION  ·  {_AXIS_LABEL[axis]} @ {axis.upper()}={offset:g}   ({_scale_label(denom)})"
    y = view.oy - _MARGIN_MM * 0.55 - h * 2.6
    t = msp.add_text(label, dxfattribs={"layer": "TEXT", "height": h})
    t.set_placement((view.ox + paper_w / 2, y), align=TextEntityAlignment.MIDDLE_CENTER)


# `_uv` is imported lazily here to avoid a circular-looking import at module top (shopdrawing is a peer).
from backends.shopdrawing import _uv  # noqa: E402

# Module-level self-registration (a backend is added by import + register, never a loop change).
from backends.registry import register as _register  # noqa: E402
import sys as _sys  # noqa: E402

_register(_sys.modules[__name__])
