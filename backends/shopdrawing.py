"""Conventioned shop-drawing backend — the moat (BRIEF §7, P2 seed; the P1 shop-drawing deliverable).

A *conventioned* drawing is not a screenshot and not a free HLR projection — it is a sheet a
fabricator can build from: a third-angle multi-view arrangement, dimensions with witness lines and
arrows, hidden-line and centre-line conventions, hole/feature callouts, a scale, and a title block.
IFC "barely carries annotation" and ~41% of BIM→practice drawing work is still manual (BRIEF §7),
which is exactly why this surface is a moat.

THE KEY DESIGN CHOICE — semantics, not topology. We do NOT lean on OCCT HLR (fragile, view-frame
ambiguous, hidden edges unreliable — measured, see git history). Instead the drawing is derived from
the IR's SEMANTICS: the true silhouette from the solid's straight edges, plus a feature overlay
authored from what the IR *knows* — "this is a ⌀9 hole THRU at (20, 0)". That semantic knowledge is
precisely what a kernel screenshot cannot reconstruct, and what lets Ludwig draw holes as proper
hidden lines + centre-lines + callouts in views where they are not even real B-rep edges.

All drafting conventions (sheet, scale ladder, line weights, title block, projection angle) live in
`standards.yaml: drawing` — the house style is data a non-coder edits, never code.

Robust by construction: every view / feature / dimension is best-effort and isolated, so one OCCT
or ezdxf hiccup degrades that detail, never the sheet. The registry already isolates the backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

name = "shop_drawing"
fmt = "dxf"
fabrication = False   # a drawing is a derived view, not a gated fabrication file

# Built-in fallbacks if standards.yaml: drawing is absent (the engine never hard-depends on it).
_DEFAULTS = {
    "projection": "third_angle",
    "sheet": {"width_mm": 420, "height_mm": 297, "margin_mm": 12},
    "scale_ladder": [1, 2, 5, 10, 20, 50, 100, 200, 500],
    "text": {"dim_height_mm": 3.0, "arrow_size_mm": 2.5, "title_height_mm": 4.0, "note_height_mm": 2.5},
    "line_weights_mm": {"visible": 0.35, "hidden": 0.18, "centre": 0.13, "dimension": 0.13, "border": 0.50},
    "title_block": {"width_mm": 180, "height_mm": 64, "org": "LUDWIG — generated"},
    "finish_map": {},
}

_GAP_MM = 28.0    # paper gap between adjacent views (room for dims between them)
_DIM_MM = 26.0    # paper margin reserved around the view cluster for dimensions
_HOLE_DIM_CAP = 6 # dimension positions for at most this many holes before relying on the callout


# --------------------------------------------------------------------------- #
# the view model
# --------------------------------------------------------------------------- #

@dataclass
class _View:
    """One orthographic view placed on the sheet. (u, v) are the view's in-plane MODEL axes
    (true mm); px/py map them to paper coordinates at the chosen scale."""
    key: str           # projection key: FRONT | TOP | RIGHT (drives _uv)
    title: str         # human label printed under the view, e.g. "FRONT ELEVATION"
    ox: float          # paper x of the view's lower-left corner
    oy: float          # paper y of the view's lower-left corner
    umin: float        # model-space minimum of the horizontal in-plane axis
    vmin: float        # model-space minimum of the vertical in-plane axis
    s: float           # paper mm per model mm (= 1 / scale_denominator)

    def px(self, u: float) -> float:
        return self.ox + (u - self.umin) * self.s

    def py(self, v: float) -> float:
        return self.oy + (v - self.vmin) * self.s

    def p(self, u: float, v: float) -> tuple[float, float]:
        return (self.px(u), self.py(v))


def _uv(view_key: str, x: float, y: float, z: float) -> tuple[float, float]:
    """Project a 3D model point to a view's (u, v) in-plane axes.
    FRONT looks along -Y (u=length x, v=height z); TOP looks along -Z (u=x, v=depth y);
    RIGHT looks along -X (u=depth y, v=height z)."""
    if view_key == "FRONT":
        return (x, z)
    if view_key == "TOP":
        return (x, y)
    return (y, z)  # RIGHT


# --------------------------------------------------------------------------- #
# backend entry point
# --------------------------------------------------------------------------- #

def compile(ir, out_dir) -> Path:  # noqa: A001 - matches the Backend protocol
    """Author a conventioned multi-view, dimensioned, title-blocked DXF shop drawing; return its path.
    Also writes a best-effort PNG preview alongside it (makes the moat visible) when matplotlib is present."""
    if ir.geometry is None:
        raise ValueError(f"element {ir.id!r} has no geometry to draw")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ir.id}.dxf"

    doc = _build_sheet(ir)
    doc.saveas(str(path))
    _render_preview(path, doc)
    return path


def _conf() -> dict:
    """Drawing conventions from standards.yaml merged over the built-in defaults."""
    try:
        from toolkit.standards import drawing as _drawing
        cfg = _drawing()
    except Exception:
        cfg = {}
    merged = {**_DEFAULTS, **cfg}
    for k, v in _DEFAULTS.items():           # one level of dict merge for the nested sections
        if isinstance(v, dict):
            merged[k] = {**v, **(cfg.get(k, {}) or {})}
    return merged


def _build_sheet(ir):
    import ezdxf

    cfg = _conf()
    sheet = cfg["sheet"]
    sw, sh, margin = float(sheet["width_mm"]), float(sheet["height_mm"]), float(sheet["margin_mm"])
    txt = cfg["text"]
    lw = cfg["line_weights_mm"]
    tb = cfg["title_block"]

    doc = ezdxf.new("R2010", setup=True)     # setup=True loads HIDDEN/CENTER linetypes + text styles
    doc.header["$INSUNITS"] = 4              # millimetres
    doc.header["$MEASUREMENT"] = 1           # metric
    doc.header["$LUNITS"] = 2                # decimal
    msp = doc.modelspace()

    _layers(doc, lw)

    # ---- measure the part ----
    xmin, xmax, ymin, ymax, zmin, zmax = _bbox(ir.geometry)
    L, W, H = xmax - xmin, ymax - ymin, zmax - zmin

    # ---- choose the scale + lay the three views out (third- or first-angle) ----
    denom = _choose_scale(cfg, L, W, H, sw, sh, margin, float(tb["height_mm"]))
    s = 1.0 / denom
    views = _layout(cfg, xmin, ymin, zmin, L, W, H, s, sw, sh, margin, float(tb["height_mm"]))

    # ---- the LUDWIG dimension style (text reads TRUE mm via DIMLFAC = scale denominator) ----
    _dimstyle(doc, txt, denom)

    # ---- per view: outline (true silhouette) + semantic feature overlay ----
    edges = _straight_edges(ir.geometry)
    features = [f for f in getattr(ir, "features", []) if isinstance(f, dict)]
    paper_w = {"FRONT": L * s, "TOP": L * s, "RIGHT": W * s}
    for k, v in views.items():
        _draw_outline(msp, v, edges, xmin, xmax, ymin, ymax, zmin, zmax)
        _view_title(msp, v, paper_w[k], txt)
    _draw_features(msp, views, features, zmin, zmax)

    # ---- dimensions: overall extents always; hole positions where they read cleanly ----
    _dimension(msp, views, L, W, H, features)

    # ---- general notes, then the sheet frame + title block ----
    _notes(msp, cfg, features, sw, margin, tb, txt)
    _frame_and_titleblock(msp, ir, cfg, denom, L, W, H, sw, sh, margin, tb, txt)

    return doc


# --------------------------------------------------------------------------- #
# kernel queries (lazy; isolated so a hiccup degrades a detail, not the sheet)
# --------------------------------------------------------------------------- #

def _bbox(handle):
    bb = handle.solid().val().BoundingBox()
    return bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax


def _straight_edges(handle):
    """The solid's straight (LINE) edges as 3D segments — the true silhouette of a prismatic part.
    Circular edges (hole rims) are deliberately skipped: holes are authored from the IR semantics
    so they appear correctly (hidden lines + centre-lines) in views where their rims are not edges."""
    try:
        segs = []
        for e in handle.solid().val().Edges():
            try:
                if e.geomType() != "LINE":
                    continue
                a = e.startPoint().toTuple()
                b = e.endPoint().toTuple()
                segs.append((a, b))
            except Exception:
                continue
        return segs
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# layout + scale
# --------------------------------------------------------------------------- #

def _content_size(L, W, H, s):
    """Paper size of the three-view cluster (front + top stacked vertically, right beside front)."""
    pl, pw, ph = L * s, W * s, H * s
    return pl + _GAP_MM + pw, ph + _GAP_MM + pw   # (width, height)


def _choose_scale(cfg, L, W, H, sw, sh, margin, tb_h) -> float:
    """Pick the scale that best FILLS the drawing area without overflowing — so a small part is
    enlarged and a large part reduced, both landing as a well-proportioned sheet (not a speck)."""
    avail_w = sw - 2 * margin - 2 * _DIM_MM
    avail_h = sh - 2 * margin - tb_h - 2 * _DIM_MM
    ladder = [float(d) for d in cfg["scale_ladder"]] or [1.0]
    fitting = []
    for denom in ladder:
        cw, ch = _content_size(L, W, H, 1.0 / denom)
        fill = max(cw / avail_w, ch / avail_h)
        if fill <= 1.0:
            fitting.append((fill, denom))
    if fitting:
        return max(fitting)[1]      # largest fill that still fits
    return max(ladder)              # nothing fits — smallest scale, let it overflow (rare)


def _scale_label(denom: float) -> str:
    """'1:20' for a reduction, '2:1' for an enlargement, '1:1' for full size."""
    if denom < 1:
        return f"{round(1.0 / denom):g}:1"
    return f"1:{denom:g}"


def _layout(cfg, xmin, ymin, zmin, L, W, H, s, sw, sh, margin, tb_h) -> dict:
    pl, pw, ph = L * s, W * s, H * s
    content_w, content_h = pl + _GAP_MM + pw, ph + _GAP_MM + pw

    # Centre the cluster in the area above the title block, leaving the dim margin on every side.
    area_x0, area_x1 = margin + _DIM_MM, sw - margin - _DIM_MM
    area_y0, area_y1 = margin + tb_h + _DIM_MM, sh - margin - _DIM_MM
    fx = area_x0 + max(0.0, (area_x1 - area_x0 - content_w) / 2)
    fy = area_y0 + max(0.0, (area_y1 - area_y0 - content_h) / 2)

    third_angle = cfg.get("projection", "third_angle") != "first_angle"
    # FRONT bottom-left at (fx, fy). Third angle: plan ABOVE front, right view to the RIGHT.
    top_oy = fy + ph + _GAP_MM if third_angle else fy - _GAP_MM - pw
    right_ox = fx + pl + _GAP_MM if third_angle else fx - _GAP_MM - pw

    return {
        "FRONT": _View("FRONT", "FRONT ELEVATION", fx, fy, xmin, zmin, s),
        "TOP":   _View("TOP", "PLAN", fx, top_oy, xmin, ymin, s),
        "RIGHT": _View("RIGHT", "SIDE", right_ox, fy, ymin, zmin, s),
    }


# --------------------------------------------------------------------------- #
# DXF setup
# --------------------------------------------------------------------------- #

def _layers(doc, lw) -> None:
    import ezdxf
    mm = lambda key, d: int(round(float(lw.get(key, d)) * 100))  # noqa: E731 - ezdxf lineweight is 1/100 mm
    spec = [
        ("VISIBLE",   ezdxf.colors.WHITE,  "CONTINUOUS", mm("visible", 0.35)),
        ("HIDDEN",    ezdxf.colors.CYAN,    "HIDDEN",     mm("hidden", 0.18)),
        ("CENTRE",    ezdxf.colors.RED,     "CENTER",     mm("centre", 0.13)),
        ("DIMENSION", ezdxf.colors.YELLOW,  "CONTINUOUS", mm("dimension", 0.13)),
        ("TEXT",      ezdxf.colors.GREEN,   "CONTINUOUS", mm("dimension", 0.13)),
        ("BORDER",    ezdxf.colors.WHITE,   "CONTINUOUS", mm("border", 0.50)),
    ]
    existing = {linetype.dxf.name for linetype in doc.linetypes}
    for lname, color, ltype, weight in spec:
        lt = ltype if ltype in existing else "CONTINUOUS"
        doc.layers.add(lname, color=color, linetype=lt, lineweight=weight)


def _dimstyle(doc, txt, denom) -> None:
    """A drafting dimension style. DIMLFAC = the scale denominator, so a paper distance measured on a
    1:denom drawing displays as the TRUE millimetre value — the professional mechanism, not a text hack."""
    if "LUDWIG" in doc.dimstyles:
        return
    ds = doc.dimstyles.new("LUDWIG")
    d = ds.dxf
    d.dimtxt = float(txt["dim_height_mm"])     # text height (paper mm)
    d.dimasz = float(txt["arrow_size_mm"])     # arrowhead size (paper mm)
    d.dimexe = 1.25                            # extension line past the dim line
    d.dimexo = 1.0                             # extension line offset from the geometry
    d.dimgap = 1.0                             # gap around the text
    d.dimdec = 0                               # whole millimetres
    d.dimlfac = float(denom)                   # measurement → true mm
    d.dimtad = 1                               # text above the dimension line
    d.dimtih = 0                               # text aligned with the dim line (not horizontal)
    d.dimtoh = 0
    d.dimclrt = 3                              # text colour (green), matches the TEXT layer
    try:
        d.dimtxsty = "Standard"
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# outline + feature overlay
# --------------------------------------------------------------------------- #

def _draw_outline(msp, view, edges, xmin, xmax, ymin, ymax, zmin, zmax) -> None:
    """Draw the view's silhouette from the solid's straight edges; fall back to the bbox rectangle."""
    drawn = 0
    for a, b in edges:
        ua, va = _uv(view.key, *a)
        ub, vb = _uv(view.key, *b)
        p0, p1 = view.p(ua, va), view.p(ub, vb)
        if abs(p0[0] - p1[0]) < 1e-9 and abs(p0[1] - p1[1]) < 1e-9:
            continue   # edge parallel to the view direction → collapses to a point
        msp.add_line(p0, p1, dxfattribs={"layer": "VISIBLE"})
        drawn += 1
    if drawn == 0:     # robust fallback: a clean bounding rectangle
        if view.key == "FRONT":
            umin, umax, vmin, vmax = xmin, xmax, zmin, zmax
        elif view.key == "TOP":
            umin, umax, vmin, vmax = xmin, xmax, ymin, ymax
        else:
            umin, umax, vmin, vmax = ymin, ymax, zmin, zmax
        corners = [view.p(umin, vmin), view.p(umax, vmin), view.p(umax, vmax), view.p(umin, vmax)]
        msp.add_lwpolyline(corners, close=True, dxfattribs={"layer": "VISIBLE"})


def _view_title(msp, view, paper_w, txt) -> None:
    """A centred view name beneath each view, below its dimension band (always-clear placement)."""
    from ezdxf.enums import TextEntityAlignment
    h = float(txt["note_height_mm"])
    y = view.oy - _DIM_MM * 0.55 - h * 2.4
    t = msp.add_text(view.title, dxfattribs={"layer": "TEXT", "height": h})
    t.set_placement((view.ox + paper_w / 2, y), align=TextEntityAlignment.MIDDLE_CENTER)


def _draw_features(msp, views, features, zmin, zmax) -> None:
    """Overlay holes/anchors authored from IR semantics: a visible circle in the plan, hidden walls +
    a centre-line in the elevations. This is the conventioned detail HLR cannot give us."""
    front, top, right = views["FRONT"], views["TOP"], views["RIGHT"]
    for f in features:
        try:
            cx, cy = f["at"]
            r = float(f["diameter"]) / 2.0
            through = bool(f.get("through", True))
            depth = f.get("depth")
            # PLAN: a real circle on the top face + a centre cross.
            c = top.p(cx, cy)
            rp = r * top.s
            msp.add_circle(c, rp, dxfattribs={"layer": "VISIBLE"})
            _centre_cross(msp, c, rp)
            # ELEVATIONS: hole axis is along Z. In FRONT the wall positions vary in x; in SIDE, in y.
            # A through hole spans the full height; a blind anchor descends `depth` from the top (+z).
            v_top = zmax
            v_bot = zmin if through else (zmax - float(depth) if depth else zmin)
            _hole_in_elevation(msp, front, cx, r, v_top, v_bot)
            _hole_in_elevation(msp, right, cy, r, v_top, v_bot)
        except Exception:
            continue   # a malformed feature never breaks the sheet


def _hole_in_elevation(msp, view, axis_u, r, v_top, v_bot) -> None:
    """Two dashed hidden walls at axis_u ± r spanning [v_bot, v_top], plus a centre-line on the axis."""
    for du in (-r, r):
        msp.add_line(view.p(axis_u + du, v_bot), view.p(axis_u + du, v_top),
                     dxfattribs={"layer": "HIDDEN"})
    # centre-line, extended a little past the material
    ext = (view.py(v_top) - view.py(v_bot)) * 0.12 + 2.0
    msp.add_line((view.px(axis_u), view.py(v_bot) - ext), (view.px(axis_u), view.py(v_top) + ext),
                 dxfattribs={"layer": "CENTRE"})


def _centre_cross(msp, c, rp) -> None:
    ext = rp + max(2.0, rp * 0.3)
    msp.add_line((c[0] - ext, c[1]), (c[0] + ext, c[1]), dxfattribs={"layer": "CENTRE"})
    msp.add_line((c[0], c[1] - ext), (c[0], c[1] + ext), dxfattribs={"layer": "CENTRE"})


# --------------------------------------------------------------------------- #
# dimensions
# --------------------------------------------------------------------------- #

def _hdim(msp, x1, x2, y_feat, y_line) -> None:
    msp.add_linear_dim(base=(x1, y_line), p1=(x1, y_feat), p2=(x2, y_feat), angle=0,
                       dimstyle="LUDWIG", dxfattribs={"layer": "DIMENSION"}).render()


def _vdim(msp, y1, y2, x_feat, x_line) -> None:
    msp.add_linear_dim(base=(x_line, y1), p1=(x_feat, y1), p2=(x_feat, y2), angle=90,
                       dimstyle="LUDWIG", dxfattribs={"layer": "DIMENSION"}).render()


def _dimension(msp, views, L, W, H, features) -> None:
    front, top = views["FRONT"], views["TOP"]
    off = _DIM_MM * 0.55
    try:
        # Overall length (below front) + height (left of front).
        _hdim(msp, front.px(front.umin), front.px(front.umin + L), front.oy, front.oy - off)
        _vdim(msp, front.py(front.vmin), front.py(front.vmin + H), front.ox, front.ox - off)
        # Overall depth/width (left of plan).
        _vdim(msp, top.py(top.vmin), top.py(top.vmin + W), top.ox, top.ox - off)
    except Exception:
        pass
    # Hole positions in the plan, from the lower-left datum (cap to avoid clutter; the callout carries the rest).
    holes = [f for f in features if f.get("kind") == "hole"][:_HOLE_DIM_CAP]
    step = 6.0
    for i, f in enumerate(holes):
        try:
            cx, cy = f["at"]
            _hdim(msp, top.px(top.umin), top.px(cx), top.py(top.vmin + W), top.py(top.vmin + W) + off + i * step)
            _vdim(msp, top.py(top.vmin), top.py(cy), top.px(top.umin + L), top.px(top.umin + L) + off + i * step)
        except Exception:
            continue


# --------------------------------------------------------------------------- #
# callouts + title block
# --------------------------------------------------------------------------- #

def _feature_callouts(features) -> list[str]:
    """Group identical features into conventioned callouts: e.g. '2× ⌀9 (M8) THRU'."""
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for f in features:
        key = (round(float(f["diameter"]), 3), bool(f.get("through", True)),
               f.get("thread"), f.get("kind"), f.get("depth"))
        if key not in groups:
            groups[key] = {"n": 0}
            order.append(key)
        groups[key]["n"] += 1
    out = []
    for key in order:
        dia, through, thread, kind, depth = key
        label = f"{groups[key]['n']}× ⌀{dia:g}"
        if thread:
            label += f" ({thread})"
        label += " THRU" if through else (f" ↧{float(depth):g} DEEP" if depth else " BLIND")
        if kind == "anchor":
            label += " CAST-IN ANCHOR"
        out.append(label)
    return out


def _notes(msp, cfg, features, sw, margin, tb, txt) -> None:
    """A general-notes block in the clear band beside the title block (bottom-left). No leaders to
    collide with the views — the centre-marks already locate every feature; the notes carry intent."""
    h = float(txt["note_height_mm"])
    th = float(tb["height_mm"])
    x = margin + 4.0
    top = margin + th - h
    line = h * 1.7

    notes = ["ALL DIMENSIONS IN MILLIMETRES.",
             f"PROJECTION: {('FIRST' if cfg.get('projection') == 'first_angle' else 'THIRD')} ANGLE."]
    notes += _feature_callouts(features)

    _text(msp, "NOTES:", x, top, h, layer="TEXT")
    for i, note in enumerate(notes, 1):
        y = top - i * line
        if y < margin + 2:        # ran out of band — stop rather than overflow the border
            break
        _text(msp, f"{i}.  {note}", x + 2.0, y, h, layer="TEXT")


def _text(msp, s, x, y, h, layer="TEXT") -> None:
    t = msp.add_text(s, dxfattribs={"layer": layer, "height": h})
    t.set_placement((x, y))


def _frame_and_titleblock(msp, ir, cfg, denom, L, W, H, sw, sh, margin, tb, txt) -> None:
    # sheet border
    m = margin
    msp.add_lwpolyline([(m, m), (sw - m, m), (sw - m, sh - m), (m, sh - m)],
                       close=True, dxfattribs={"layer": "BORDER"})
    # title block, bottom-right inside the border
    tw, th = float(tb["width_mm"]), float(tb["height_mm"])
    x0, y0 = sw - m - tw, m
    x1, y1 = sw - m, m + th
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True,
                       dxfattribs={"layer": "BORDER"})
    rows = 4
    for i in range(1, rows):
        yy = y0 + th * i / rows
        msp.add_line((x0, yy), (x1, yy), dxfattribs={"layer": "BORDER"})
    midx = x0 + tw * 0.5
    msp.add_line((midx, y0), (midx, y0 + th * (rows - 1) / rows), dxfattribs={"layer": "BORDER"})

    th_h = float(txt["title_height_mm"])
    no_h = float(txt["note_height_mm"])
    finish = (cfg.get("finish_map", {}) or {}).get(ir.type) or _material_name(ir.type)
    pad = 2.5
    rh = th / rows

    def cell(cx, row, s, height):
        t = msp.add_text(s, dxfattribs={"layer": "TEXT", "height": height})
        t.set_placement((cx + pad, y0 + rh * row + (rh - height) / 2))

    # row 3 (top): org banner
    cell(x0, 3, str(tb.get("org", "LUDWIG — generated")), no_h)
    # row 2: title (part name) spanning, big
    cell(x0, 2, (ir.name or ir.id).upper(), th_h)
    # row 1: type | material
    cell(x0, 1, f"TYPE: {ir.type}", no_h)
    cell(midx, 1, f"MATL: {finish}", no_h)
    # row 0 (bottom): scale + units | overall size | dwg id
    cell(x0, 0, f"SCALE {_scale_label(denom)}  ·  mm", no_h)
    cell(midx, 0, f"{L:g}×{W:g}×{H:g}  ·  {ir.id}", no_h)


def _material_name(type_: str) -> str:
    try:
        from toolkit.standards import load
        std = load()
        mkey = std.get("ifc_material_map", {}).get(type_)
        if mkey:
            return std.get("materials", {}).get(mkey, {}).get("ifc_material", mkey)
    except Exception:
        pass
    return "—"


# --------------------------------------------------------------------------- #
# preview render (best-effort; the moat, made visible)
# --------------------------------------------------------------------------- #

def _render_preview(dxf_path: Path, doc) -> Path | None:
    """Render the sheet to a PNG via ezdxf's matplotlib backend. Never raises — a missing matplotlib
    or a render hiccup simply yields no preview; the DXF is the deliverable."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

        fig = plt.figure(figsize=(16.54, 11.69))   # A3 in inches
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(doc.modelspace(), finalize=True)
        png = dxf_path.with_suffix(".png")
        fig.savefig(str(png), dpi=96, facecolor="white")
        plt.close(fig)
        return png
    except Exception:
        return None


# Module-level self-registration (a backend is added by import + register, never a loop change).
from backends.registry import register as _register  # noqa: E402
import sys as _sys  # noqa: E402

_register(_sys.modules[__name__])
