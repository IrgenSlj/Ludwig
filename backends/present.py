"""Presentation auto-assembly backend — a client-ready one-page sheet (BRIEF P3).

A *presentation* is not a new authored artifact: it is a DERIVED PROJECTION of the IR that
COMPOSES the already-derived backends (the conventioned shop drawing, the elevation, the named
dimensions, the fabrication deliverables) into one beautifully-typeset sheet a non-engineer can
read at a glance. It owns no geometry and invents no truth — it arranges what the IR and the other
backends have already produced.

Self-contained and dependency-light by construction: a single HTML file with inline CSS, stdlib
only (no pip deps, no matplotlib). It matches Ludwig's art direction — warm paper-white / deep
graphite, a humanist sans for UI text and a drafting mono for dimensions, hairline rules,
restrained (docs/UX_BRIEF.md "Art direction").

Robust by construction: every optional piece (bbox, finish, preview image, sibling deliverables)
is best-effort and isolated, so one missing artifact degrades that detail, never the sheet. The
heavy kernel (cadquery) is imported lazily and only to read a bounding box — its absence simply
drops the overall-size line.
"""
from __future__ import annotations

import html
from pathlib import Path

name = "present"
fmt = "html"
fabrication = False   # a presentation is a derived view, never a gated fabrication file

# Sibling deliverables linked from the sheet, in presentation order: (suffix, label).
_DELIVERABLES = [
    (".step", "STEP", "Solid model — fabrication / CAD interchange"),
    (".ifc", "IFC", "BIM model — coordination / handover"),
    (".dxf", "DXF", "Conventioned shop drawing"),
    (".svg", "SVG", "Elevation preview"),
    (".py", "PY", "Re-promptable program — the source of truth"),
]


# --------------------------------------------------------------------------- #
# backend entry point
# --------------------------------------------------------------------------- #

def compile(ir, out_dir) -> Path:  # noqa: A001 - matches the Backend protocol
    """Auto-assemble a client-ready one-page presentation sheet (HTML); return its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ir.id}.present.html"
    path.write_text(_sheet(ir, out_dir), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# data gathering (every reader is best-effort — a hiccup drops a detail, not the sheet)
# --------------------------------------------------------------------------- #

def _bbox(ir):
    """Overall (L, W, H) in mm from the solid's bounding box, or None if unreadable.
    Lazy + isolated: a missing cadquery / ungeneratable solid simply drops the size line."""
    try:
        bb = ir.geometry.solid().val().BoundingBox()
        return (bb.xmax - bb.xmin, bb.ymax - bb.ymin, bb.zmax - bb.zmin)
    except Exception:
        return None


def _finish(ir) -> str:
    """The material/finish string: standards.yaml drawing.finish_map[type], else the IFC material."""
    try:
        from toolkit.standards import drawing as _drawing
        fin = (_drawing().get("finish_map", {}) or {}).get(ir.type)
        if fin:
            return str(fin)
    except Exception:
        pass
    return _material_name(ir.type)


def _material_name(type_: str) -> str:
    """Fall back to the IFC material name for the element type (matches the shop-drawing backend)."""
    try:
        from toolkit.standards import load
        std = load()
        mkey = std.get("ifc_material_map", {}).get(type_)
        if mkey:
            return std.get("materials", {}).get(mkey, {}).get("ifc_material", mkey)
    except Exception:
        pass
    return "—"


def _preview(ir, out_dir: Path):
    """The shop-drawing PNG preview if present, else the SVG elevation. Returned as a relative
    src so the sheet stays portable beside its siblings; None if neither exists."""
    for suffix in (".png", ".svg"):
        if (out_dir / f"{ir.id}{suffix}").exists():
            return f"{ir.id}{suffix}"
    return None


def _deliverables(ir, out_dir: Path) -> list[tuple[str, str, str]]:
    """The sibling artifacts that actually exist in out_dir, as (href, label, note)."""
    out = []
    for suffix, label, note in _DELIVERABLES:
        fname = f"{ir.id}{suffix}"
        if (out_dir / fname).exists():
            out.append((fname, label, note))
    return out


# --------------------------------------------------------------------------- #
# the sheet (inline CSS — self-contained, stdlib only)
# --------------------------------------------------------------------------- #

def _sheet(ir, out_dir: Path) -> str:
    e = html.escape
    title = e(getattr(ir, "name", "") or ir.id)
    type_ = e(getattr(ir, "type", "") or "Part")
    finish = e(_finish(ir))
    part_id = e(str(ir.id))

    bbox = _bbox(ir)
    size = f"{bbox[0]:g} × {bbox[1]:g} × {bbox[2]:g} mm" if bbox else "—"

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title} — LUDWIG</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n<body>\n"
        '<main class="sheet">\n'
        f"{_title_block(title, type_, finish, size, part_id)}\n"
        f"{_figure(ir, out_dir)}\n"
        '<section class="cols">\n'
        f"{_schedule(ir)}\n"
        f"{_deliverables_block(ir, out_dir)}\n"
        "</section>\n"
        f"{_footer(part_id)}\n"
        "</main>\n"
        "</body>\n</html>\n"
    )


def _title_block(title, type_, finish, size, part_id) -> str:
    return (
        '<header class="title-block">\n'
        '  <div class="title-main">\n'
        f'    <h1>{title}</h1>\n'
        f'    <div class="subtitle"><span class="mono">{part_id}</span> · {type_}</div>\n'
        "  </div>\n"
        '  <dl class="specs">\n'
        f'    <div><dt>Material / finish</dt><dd>{finish}</dd></div>\n'
        f'    <div><dt>Overall size</dt><dd class="mono">{size}</dd></div>\n'
        '    <div><dt>Mark</dt><dd>LUDWIG — generated</dd></div>\n'
        "  </dl>\n"
        "</header>\n"
    )


def _figure(ir, out_dir: Path) -> str:
    src = _preview(ir, out_dir)
    if not src:
        return (
            '<figure class="drawing drawing--empty">\n'
            '  <div class="placeholder">No derived drawing yet</div>\n'
            '  <figcaption>Conventioned shop drawing</figcaption>\n'
            "</figure>\n"
        )
    return (
        '<figure class="drawing">\n'
        f'  <img src="{html.escape(src, quote=True)}" alt="Conventioned drawing of {html.escape(str(ir.id))}">\n'
        '  <figcaption>Conventioned shop drawing — derived from the IR</figcaption>\n'
        "</figure>\n"
    )


def _schedule(ir) -> str:
    rows = []
    for d in getattr(ir, "manifest", []) or []:
        try:
            name_ = html.escape(str(d.name))
            value = f"{d.value:g}" if isinstance(d.value, (int, float)) else html.escape(str(d.value))
            unit = html.escape(str(getattr(d, "unit", "") or ""))
        except Exception:
            continue
        rows.append(
            f'      <tr><td class="dim-name">{name_}</td>'
            f'<td class="mono dim-val">{value}</td>'
            f'<td class="mono dim-unit">{unit}</td></tr>'
        )
    body = "\n".join(rows) if rows else (
        '      <tr><td class="dim-name" colspan="3">No named dimensions</td></tr>'
    )
    return (
        '<section class="panel schedule">\n'
        "  <h2>Dimension schedule</h2>\n"
        '  <table class="dim-table">\n'
        "    <thead><tr><th>Name</th><th>Value</th><th>Unit</th></tr></thead>\n"
        f"    <tbody>\n{body}\n    </tbody>\n"
        "  </table>\n"
        "</section>\n"
    )


def _deliverables_block(ir, out_dir: Path) -> str:
    items = _deliverables(ir, out_dir)
    if items:
        body = "\n".join(
            f'      <li><a href="{html.escape(href, quote=True)}">'
            f'<span class="mono tag">{html.escape(label)}</span>'
            f"<span class=\"note\">{html.escape(note)}</span></a></li>"
            for href, label, note in items
        )
    else:
        body = '      <li class="empty">No sibling deliverables in this folder yet</li>'
    return (
        '<section class="panel deliverables">\n'
        "  <h2>Deliverables</h2>\n"
        f'  <ul class="deliverable-list">\n{body}\n  </ul>\n'
        "</section>\n"
    )


def _footer(part_id) -> str:
    return (
        '<footer class="sheet-foot">\n'
        '  <span class="mark">LUDWIG</span>\n'
        '  <span class="sep">·</span>\n'
        "  <span>AI-native precision design</span>\n"
        '  <span class="sep">·</span>\n'
        f'  <span class="mono">{part_id}</span>\n'
        "</footer>\n"
    )


# --------------------------------------------------------------------------- #
# art direction — warm paper-white / deep graphite, humanist sans + drafting mono,
# hairline rules, restrained (docs/UX_BRIEF.md). Inline so the sheet is self-contained.
# --------------------------------------------------------------------------- #

_CSS = """
:root {
  --paper: #efece7;
  --graphite: #1c1a17;
  --muted: #6e675b;
  --ink-soft: #262320;
  --hairline: rgba(28, 26, 23, 0.16);
  --hairline-strong: rgba(28, 26, 23, 0.42);
  --accent: #8a5a2b;
  --sans: system-ui, -apple-system, "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  --mono: "SFMono-Regular", "JetBrains Mono", "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  background: #e4e0d9;
  color: var(--graphite);
  font-family: var(--sans);
  -webkit-font-smoothing: antialiased;
  font-feature-settings: "kern" 1, "liga" 1;
}
.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.sheet {
  max-width: 920px;
  margin: 32px auto;
  padding: 44px 48px 30px;
  background: var(--paper);
  border: 1px solid var(--hairline);
  box-shadow: 0 1px 0 rgba(255,255,255,0.5) inset, 0 18px 48px rgba(28,26,23,0.10);
}

/* title block */
.title-block {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 32px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--hairline-strong);
}
.title-main h1 {
  margin: 0;
  font-size: 30px;
  font-weight: 600;
  letter-spacing: -0.012em;
  line-height: 1.05;
}
.subtitle {
  margin-top: 8px;
  color: var(--muted);
  font-size: 13px;
  letter-spacing: 0.01em;
}
.subtitle .mono { color: var(--ink-soft); }
.specs {
  margin: 0;
  display: grid;
  gap: 9px;
  min-width: 240px;
  text-align: right;
}
.specs div { display: grid; gap: 1px; }
.specs dt {
  margin: 0;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.13em;
  color: var(--muted);
}
.specs dd { margin: 0; font-size: 14px; }

/* drawing figure */
.drawing {
  margin: 22px 0 6px;
  padding: 0;
}
.drawing img {
  display: block;
  width: 100%;
  height: auto;
  background: #fff;
  border: 1px solid var(--hairline);
}
.drawing figcaption {
  margin-top: 8px;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--muted);
  text-align: center;
}
.drawing--empty .placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 220px;
  background: repeating-linear-gradient(
    45deg, transparent, transparent 9px, rgba(28,26,23,0.05) 9px, rgba(28,26,23,0.05) 10px);
  border: 1px solid var(--hairline);
  color: var(--muted);
  font-size: 13px;
  letter-spacing: 0.04em;
}

/* two-column body */
.cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 34px;
  margin-top: 24px;
}
.panel h2 {
  margin: 0 0 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--muted);
  padding-bottom: 7px;
  border-bottom: 1px solid var(--hairline);
}

/* dimension schedule */
.dim-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.dim-table thead th {
  text-align: left;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--muted);
  padding: 0 0 6px;
  border-bottom: 1px solid var(--hairline);
}
.dim-table thead th:nth-child(2), .dim-table thead th:nth-child(3) { text-align: right; }
.dim-table td { padding: 6px 0; border-bottom: 1px solid var(--hairline); }
.dim-name { color: var(--ink-soft); }
.dim-val { text-align: right; }
.dim-unit { text-align: right; color: var(--muted); width: 2.6em; }

/* deliverables */
.deliverable-list { list-style: none; margin: 0; padding: 0; }
.deliverable-list li { border-bottom: 1px solid var(--hairline); }
.deliverable-list a {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 8px 0;
  text-decoration: none;
  color: var(--graphite);
}
.deliverable-list a:hover .note { color: var(--graphite); }
.tag {
  display: inline-block;
  min-width: 42px;
  padding: 2px 7px;
  font-size: 11px;
  letter-spacing: 0.05em;
  color: var(--paper);
  background: var(--graphite);
  text-align: center;
}
.deliverable-list .note { font-size: 12px; color: var(--muted); }
.deliverable-list .empty { padding: 8px 0; color: var(--muted); font-size: 12px; }

/* footer */
.sheet-foot {
  margin-top: 30px;
  padding-top: 14px;
  border-top: 1px solid var(--hairline-strong);
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--muted);
}
.sheet-foot .mark { font-weight: 600; letter-spacing: 0.18em; color: var(--graphite); }
.sheet-foot .sep { color: var(--hairline-strong); }

@media (max-width: 680px) {
  .sheet { padding: 28px 22px; }
  .title-block { flex-direction: column; gap: 16px; }
  .specs { text-align: left; min-width: 0; }
  .cols { grid-template-columns: 1fr; gap: 24px; }
}
"""


# Module-level self-registration (a backend is added by import + register, never a loop change).
from backends.registry import register as _register  # noqa: E402
import sys as _sys  # noqa: E402

_register(_sys.modules[__name__])
