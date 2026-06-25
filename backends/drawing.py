"""Drawing backend — OCCT HLR → SVG elevation, dims from the manifest (BRIEF §7, P0.5/S7).

CadQuery's SVG exporter performs OCCT Hidden-Line-Removal projection, so this is a real derived
view, not a screenshot. Deliberately OUTSIDE the spine gate: OCCT HLR is fragile (open correctness
bugs, perf cliffs), so the compile path treats it as best-effort and never lets it block the solid.
Conventioned architectural drawings (poché, swings, dimension strings) are the much harder P2 problem.
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
    """Project the element to an HLR SVG elevation and overlay its named dimensions; return the path."""
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
