"""Drawing backend — OCCT HLR → SVG elevation + DXF with conventioned dimensions (BRIEF §7, P2).

CadQuery's SVG exporter performs OCCT Hidden-Line-Removal projection, so SVG is a real derived
view, not a screenshot. DXF uses OCCT HLR directly via OCP bindings and ezdxf for proper vector
output with dimension lines, witness lines, and arrows.

SVG is deliberately OUTSIDE the spine gate: OCCT HLR is fragile (open correctness bugs, perf
cliffs), so the compile path treats it as best-effort and never lets it block the solid.
Conventioned DXF is the P2 drawing deliverable.
"""
from __future__ import annotations

from pathlib import Path

name = "drawing"
fmt = "svg"
fabrication = False

# A front elevation. Keep the option set small — older OCCT/CadQuery reject unknown keys, so the
# compile() falls back to a default projection if these are not accepted.
_SVG_OPTS = {
    "width": 640, "height": 420, "marginLeft": 24, "marginTop": 24,
    "showAxes": False, "projectionDir": (0, -1, 0.0001),
    "strokeWidth": 0.4, "strokeColor": (40, 40, 40),
    "hiddenColor": (170, 170, 170), "showHidden": True,
}


def compile(ir, out_dir) -> Path:  # noqa: A001 - matches the Backend protocol
    """Project the element to an HLR SVG elevation with dimension annotations; return the path."""
    import cadquery as cq

    if ir.geometry is None:
        raise ValueError(f"element {ir.id!r} has no geometry to draw")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ir.id}.svg"
    solid = ir.geometry.solid()
    try:
        cq.exporters.export(solid, str(path), exportType="SVG", opt=_SVG_OPTS)
    except Exception:  # unknown opt keys / HLR hiccup → default projection still gives a valid SVG
        cq.exporters.export(solid, str(path), exportType="SVG")
    _annotate_dims(path, ir)
    return path


# Module-level self-registration
from backends.registry import register as _register
import sys as _sys
_register(_sys.modules[__name__])


def _annotate_dims(path: Path, ir) -> None:
    """Overlay a drafting-mono dimension block from the manifest. Real dimension strings with
    arrows/witness lines are the conventioned-drawing problem (P2); this is the P0.5 honest version."""
    rows = [f'<text x="10" y="18" font-family="monospace" font-size="12" '
            f'fill="#262320">{ir.name or ir.id}</text>']
    y = 18
    for d in ir.manifest:
        y += 15
        rows.append(f'<text x="10" y="{y}" font-family="monospace" font-size="10" '
                    f'fill="#6E675B">{d.name} = {d.value:g} {d.unit}</text>')
    svg = path.read_text()
    if "</svg>" in svg:
        svg = svg.replace("</svg>", "\n".join(rows) + "\n</svg>", 1)
        path.write_text(svg)


# ---------------------------------------------------------------------------
# P2: DXF conventioned drawing (ezdxf)
# ---------------------------------------------------------------------------

fmt_dxf = "dxf"


def compile_dxf(ir, out_dir) -> Path:
    """Export a conventioned DXF elevation: OCCT HLR projection → 2D edges with dimension lines.
    Uses OCP bindings for the HLR and ezdxf for the DXF writer."""
    import ezdxf

    if ir.geometry is None:
        raise ValueError(f"element {ir.id!r} has no geometry to draw")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ir.id}.dxf"

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # mm
    msp = doc.modelspace()

    # ---- extract HLR edges ----
    visible_2d, hidden_2d = _hlr_edges_2d(ir.geometry, proj_dir=(0, -1, 0))

    # ---- visible edges (continuous) ----
    doc.layers.add("VISIBLE", color=ezdxf.colors.WHITE)
    for pts in visible_2d:
        if len(pts) >= 2:
            msp.add_lwpolyline(pts, dxfattribs={"layer": "VISIBLE", "lineweight": 50})

    # ---- hidden edges (dashed) ----
    doc.layers.add("HIDDEN", color=ezdxf.colors.CYAN)
    for pts in hidden_2d:
        if len(pts) >= 2:
            msp.add_lwpolyline(pts, dxfattribs={
                "layer": "HIDDEN", "lineweight": 25,
                "linetype": "DASHED2",
            })

    # ---- dimension lines from the manifest ----
    _add_dxf_dimensions(doc, msp, ir, visible_2d)

    doc.saveas(str(path))
    return path


def _hlr_edges_2d(handle, proj_dir=(0, -1, 0), samples=20):
    """Project a solid via OCCT HLR and return (visible_2d, hidden_2d) lists of point sequences.
    Each sequence is a list of (x, z) tuples in the projected 2D view plane (front elevation)."""
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopoDS import TopoDS

    shape = handle.solid().val().wrapped

    dx, dy, dz = proj_dir
    algo = HLRBRep_Algo()
    algo.Add(shape)
    proj = HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(dx, dy, dz)))
    algo.Projector(proj)
    algo.Update()
    algo.Select()

    hlr_shapes = HLRBRep_HLRToShape(algo)

    def _sample(compound):
        pts = []
        exp = TopExp_Explorer(compound, TopAbs_EDGE)
        while exp.More():
            edge = TopoDS.Edge(exp.Current())
            curve = BRepAdaptor_Curve(edge)
            first = curve.FirstParameter()
            last = curve.LastParameter()
            seg = []
            for i in range(samples + 1):
                t = first + (last - first) * i / samples
                p = curve.Value(t)
                seg.append((p.X(), p.Z()))  # project to X-Z plane
            pts.append(seg)
            exp.Next()
        return pts

    visible = _sample(hlr_shapes.VCompound())
    hidden = _sample(hlr_shapes.HCompound())
    return visible, hidden


def _add_dxf_dimensions(doc, msp, ir, visible_2d):
    """Add dimension lines and witness lines around the projected geometry using named dims
    from the element manifest. Positioned below and to the right of the part silhouette."""
    import ezdxf  # noqa: PLC0415

    xs = [p[0] for seg in visible_2d for p in seg] if visible_2d else [0]
    zs = [p[1] for seg in visible_2d for p in seg] if visible_2d else [0]
    if not xs or not zs:
        return
    xmin, xmax = min(xs), max(xs)
    zmin, zmax = min(zs), max(zs)
    pad = (xmax - xmin) * 0.08 or 10

    doc.layers.add("DIMENSION", color=ezdxf.colors.YELLOW)
    dim_style = "STANDARD"

    for d in ir.manifest:
        name_lower = d.name.lower()

        if name_lower in ("length", "width"):
            y_line = zmin - pad * 1.5
            x_start, x_end = xmin, xmax
            msp.add_line((x_start, zmin - pad), (x_start, y_line + pad * 0.3),
                         dxfattribs={"layer": "DIMENSION", "lineweight": 13})
            msp.add_line((x_end, zmin - pad), (x_end, y_line + pad * 0.3),
                         dxfattribs={"layer": "DIMENSION", "lineweight": 13})
            msp.add_aligned_dim(p1=(x_start, y_line), p2=(x_end, y_line),
                                dimstyle=dim_style,
                                dxfattribs={"layer": "DIMENSION"}).render()

        elif name_lower == "height":
            x_line = xmax + pad * 1.5
            y_start, y_end = zmin, zmax
            msp.add_line((xmax + pad, zmin), (x_line - pad * 0.3, zmin),
                         dxfattribs={"layer": "DIMENSION", "lineweight": 13})
            msp.add_line((xmax + pad, zmax), (x_line - pad * 0.3, zmax),
                         dxfattribs={"layer": "DIMENSION", "lineweight": 13})
            msp.add_aligned_dim(p1=(x_line, y_start), p2=(x_line, y_end),
                                dimstyle=dim_style,
                                dxfattribs={"layer": "DIMENSION"}).render()
