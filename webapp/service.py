"""compile_to_result / edit_to_result — the real compile + edit paths, as serializable data.

This is the seam the web UI binds to. It runs the genuine loop (generate/edit → execute → critic →
repair) and the genuine backends (STEP/IFC/SVG/mesh) — exactly what `cli.py` does — and returns a
plain dict so a browser, the CLI, or a test can all consume the same truth. No geometry is faked; the
prototype's timer-mock is replaced by this. The loop stays the source of truth (BRIEF §5); the web
server is just another *frontend*, like the CLI — adding it does not touch the loop ([H4]).
"""
from __future__ import annotations

import ast
import difflib
import re
from pathlib import Path
from typing import Optional

OUT = Path("out")

# extent dims a slider can tweak deterministically, mapped to their bbox axis (x,y,z)
_EXTENT_AXIS = {"length": 0, "width": 1, "thickness": 1, "height": 2}
# dims the UI exposes as direct-edit controls (a slider / face-drag). Extents bind to a bbox axis;
# the rest (diameter, stair rise/going/riser_count) are editable via literal substitution with no axis
# signature (their acceptance test is cylindrical / a re-measure, not a bbox axis).
_EDITABLE_DIMS = {"length", "width", "height", "thickness", "diameter",
                  "rise", "going", "riser_count", "depth"}


def _dims(manifest) -> list[dict]:
    """Serialize a manifest to JSON, deduped by name (last value wins). Live codegen sometimes
    register_dim's the same extent twice; the UI should show each named dim once.

    R9 — each dim also carries its binding metadata: `axis` (0/1/2 for an extent that maps to a bbox
    axis via _EXTENT_AXIS, else null) and `editable` (a direct-edit control is offered). This is the
    bridge a face-drag (R10) reads to map a picked face's world normal back to the dim it drives."""
    seen: dict[str, dict] = {}
    for d in manifest:
        seen[d.name] = {"name": d.name, "value": d.value, "unit": d.unit,
                        "axis": _EXTENT_AXIS.get(d.name),
                        "editable": d.name in _EDITABLE_DIMS}
    return list(seen.values())
_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")  # a standalone number literal (not M6, not 1.5e3)


def _comment_regions(program: str) -> list[tuple[int, int]]:
    """Char ranges that are `#` comments, so a literal echoed in a comment (e.g. the codegen's own
    `# 80 (length) × 40 …`) doesn't defeat the uniqueness check."""
    regions, off = [], 0
    for line in program.splitlines(keepends=True):
        h = line.find("#")
        if h != -1:
            regions.append((off + h, off + len(line)))
        off += len(line)
    return regions


def _substitute_unique_literal(program: str, old: float, new: float) -> Optional[str]:
    """Replace the program's literal `old` with `new` — but ONLY if `old` occurs exactly once as a
    number in CODE (comments excluded). Ambiguous (0 or >1 matches, e.g. a 30×30 square) → None, so
    the caller falls back to the LLM edit. Preserves int/float spelling so the diff is one token."""
    comments = _comment_regions(program)
    in_comment = lambda pos: any(a <= pos < b for a, b in comments)  # noqa: E731
    spans = [m for m in _NUM.finditer(program)
             if abs(float(m.group()) - old) < 1e-9 and not in_comment(m.start())]
    if len(spans) != 1:
        return None
    m = spans[0]
    txt = str(float(new)) if "." in m.group() else str(int(new))
    return program[:m.start()] + txt + program[m.end():]


def _substitute_all_literals(program: str, old: float, new: float) -> Optional[str]:
    """Replace EVERY standalone code occurrence of `old` with `new` (comments excluded).

    Unlike `_substitute_unique_literal`, this handles the common case where one physical extent is
    echoed — `box(..., 120, ...)` AND `register_dim("plate_length", 120)` — which must move together.
    The caller guards against a coincidental same-valued literal by re-measuring the intended axis
    after the rebuild. Returns None if `old` never occurs in code. Preserves int/float spelling."""
    comments = _comment_regions(program)
    in_comment = lambda pos: any(a <= pos < b for a, b in comments)  # noqa: E731
    spans = [m for m in _NUM.finditer(program)
             if abs(float(m.group()) - old) < 1e-9 and not in_comment(m.start())]
    if not spans:
        return None
    out = program
    for m in reversed(spans):  # right-to-left so earlier spans' offsets stay valid
        txt = str(float(new)) if "." in m.group() else str(int(new))
        out = out[:m.start()] + txt + out[m.end():]
    return out


def _try_fast_edit(program: str, name: str, old: float, new: float, out: Path) -> Optional[dict]:
    """Deterministic, no-LLM parametric tweak for a single extent dim. Substitute the literal,
    re-execute, and ACCEPT only if the intended axis now measures `new` and the solid is valid/
    all-pass — otherwise return None and let the caller fall back to the (correct, slower) LLM edit.
    The LLM stays the backstop; this just makes the common numeric-slider case instant."""
    axis = _EXTENT_AXIS.get(name)
    if axis is None:
        return None
    from agent.loop import Brief, LoopResult, execute, verify
    from geometry import GeometryService
    from toolkit.standards import tol_linear
    g = GeometryService()
    orig, _e = execute(program)  # baseline extents, to confirm ONLY the intended axis moves
    if orig is None or orig.geometry is None:
        return None
    orig_bb = g.bbox(orig.geometry)
    new_program = _substitute_all_literals(program, old, new)  # move all echoes of this value together
    if new_program is None:
        return None
    el, err = execute(new_program)
    if err or el is None or el.geometry is None:
        return None
    bb, tol = g.bbox(el.geometry), max(tol_linear(), 1e-3)
    # the target axis must become `new`; every OTHER extent must be unchanged. This rejects a coincidental
    # same-valued literal AND a square (editing length when length==width would move both) → fall back to LLM.
    for i in range(3):
        if abs(bb[i] - (new if i == axis else orig_bb[i])) > tol:
            return None
    crit = verify(el, Brief(prompt=""))
    if not crit.passed:
        return None
    res = LoopResult(new_program, el, crit, True, 0, None)
    result = _assemble(res, out)
    diff = list(difflib.unified_diff(program.splitlines(), new_program.splitlines(), lineterm="", n=1))
    result["diff"] = {"added": 1, "removed": 1, "text": "\n".join(diff)}
    result["fast"] = True
    return result


# R8: per-node source spans. box(id, length, width, height) → the char span of each positional extent
# literal, recovered from the program AST and matched to graph node ids in source order. This lets a
# durable edit substitute the NODE's literal directly, even when its value collides with another extent
# (a 30×30 square's length == width), which the value-based substitute-all can't disambiguate.
_OP_FUNC = {"box": "box", "hole": "hole", "clearance_hole": "hole", "anchor": "anchor",
            "place": "place", "stack": "stack", "assembly": "assembly"}
_BOX_PARAMS = ("length", "width", "height")   # box(id, length, width, height) — positional args 1..3


def _node_spans(program: str) -> dict[tuple[str, str], tuple[int, int]]:
    """{(node_id, param): (start, end)} char spans for box extent literals, by matching AST calls to
    lineage-stable node ids (op#count) in source order — the same scheme FeatureGraph assigns. Returns
    {} on a parse error or for fenced/non-straight-line programs (the caller then falls back)."""
    try:
        tree = ast.parse(program)
    except SyntaxError:
        return {}
    starts = [0]
    for line in program.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    off = lambda lineno, col: starts[lineno - 1] + col  # noqa: E731  (lineno is 1-based)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _OP_FUNC:
            calls.append((node.lineno, node.col_offset, _OP_FUNC[node.func.id], node))
    calls.sort(key=lambda c: (c[0], c[1]))
    counts: dict[str, int] = {}
    spans: dict[tuple[str, str], tuple[int, int]] = {}
    for _ln, _col, op, node in calls:
        counts[op] = counts.get(op, 0) + 1
        node_id = f"{op}#{counts[op]}"
        if op == "box":
            for i, pname in enumerate(_BOX_PARAMS, start=1):
                if i < len(node.args):
                    a = node.args[i]
                    if hasattr(a, "end_col_offset") and a.end_col_offset is not None:
                        spans[(node_id, pname)] = (off(a.lineno, a.col_offset),
                                                   off(a.end_lineno, a.end_col_offset))
    return spans


def _try_span_edit(program: str, name: str, old: float, new: float, out: Path) -> Optional[dict]:
    """R8 durable minimal-diff edit by substituting exactly the recorded node's literal span — handles
    the case `_substitute_all_literals` can't (a square's length == width), deterministically (no LLM).
    Substitute the box-extent span, re-execute, and accept only if the target axis became `new` and no
    other extent moved and the critic passes — otherwise return None to fall back to the LLM edit."""
    axis = _EXTENT_AXIS.get(name)
    if axis is None:
        return None
    entry = _graph_for(program)
    if entry["graph"] is None or entry["el"] is None or entry["el"].children:
        return None
    spans = _node_spans(program)
    targets = [spans[(nid, pname)] for (nid, pname) in _nodes_for_dim(entry["graph"], name, old)
               if (nid, pname) in spans]
    if not targets:
        return None
    from agent.loop import Brief, LoopResult, execute, verify
    from geometry import GeometryService
    from toolkit.standards import tol_linear
    g = GeometryService()
    orig = entry["el"]
    if orig.geometry is None:
        return None
    orig_bb = g.bbox(orig.geometry)
    lit = program[targets[0][0]:targets[0][1]]
    txt = str(float(new)) if "." in lit else str(int(new))
    new_program = program
    for a, b in sorted(targets, reverse=True):   # right-to-left so earlier spans stay valid
        new_program = new_program[:a] + txt + new_program[b:]
    el, err = execute(new_program)
    if err or el is None or el.geometry is None:
        return None
    bb, tol = g.bbox(el.geometry), max(tol_linear(), 1e-3)
    for i in range(3):                            # target axis becomes `new`; every other extent holds
        if abs(bb[i] - (new if i == axis else orig_bb[i])) > tol:
            return None
    crit = verify(el, Brief(prompt=""))
    if not crit.passed:
        return None
    res = LoopResult(new_program, el, crit, True, 0, None)
    result = _assemble(res, out)
    diff = list(difflib.unified_diff(program.splitlines(), new_program.splitlines(), lineterm="", n=1))
    result["diff"] = {
        "added": sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++")),
        "removed": sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---")),
        "text": "\n".join(diff)}
    result["fast"] = True
    return result


def _assemble(res, out: Path, on_event=None) -> dict:
    """Turn a LoopResult into a JSON-safe dict: IR stats, critic, render mesh, persisted artifacts.

    The fabrication gate holds — STEP/IFC are written only when the critic is all-pass (no fab file
    on a failing critic, BRIEF §5). The SVG drawing and the viewer mesh are best-effort, never block.
    `on_event` (optional) fires per derived backend so a live Activity Rail can show the derive stage.
    """
    from geometry import GeometryService

    def emit(**ev):
        if on_event:
            try:
                on_event(ev)
            except Exception:
                pass

    result: dict = {
        "program": res.program, "rounds": res.rounds, "passed": res.passed, "error": res.error,
        "id": res.ir.id if res.ir is not None else None,
        "type": res.ir.type if res.ir is not None else None,
        "bbox": None, "dims": [], "critic": [], "mesh": None, "children": [], "artifacts": {},
    }
    if res.ir is None:
        return result

    el, g = res.ir, GeometryService()
    if el.geometry is not None:
        length, width, height = g.bbox(el.geometry)
        result["bbox"] = {"length": round(length, 4), "width": round(width, 4), "height": round(height, 4)}
        try:  # the 3D render mesh for the Stage viewport — best-effort
            result["mesh"] = g.tessellate(el.geometry)
        except Exception as e:
            result["mesh_error"] = f"{type(e).__name__}: {e}"
    # An Assembly's children, each tessellated separately so the viewport can select/highlight one
    # solid at a time — "geometry is the index into the program" for multi-part models.
    for c in getattr(el, "children", []) or []:
        child = {"id": c.id, "type": c.type, "dims": _dims(c.manifest), "mesh": None}
        if c.geometry is not None:
            try:
                child["mesh"] = g.tessellate(c.geometry)
            except Exception:
                child["mesh"] = None
        result["children"].append(child)
    result["dims"] = _dims(el.manifest)
    # element_id + severity travel with each check so the UI can paint Ambient Correctness onto the
    # geometry (a WARNING-severity fail is amber/below-spec; an ERROR/CRITICAL fail is red — UX_BRIEF).
    result["critic"] = [
        {"check": c.check, "status": c.status.value, "message": c.message,
         "element_id": getattr(c, "element_id", None),
         "severity": getattr(getattr(c, "severity", None), "name", "ERROR").lower()}
        for c in (res.critique.checks if res.critique else [])
    ]

    recipe = out / f"{el.id}.py"
    recipe.write_text(res.program + "\n")
    result["artifacts"]["recipe"] = recipe.name
    if res.passed:
        from backends import all as all_backends
        for b in all_backends():
            label = {"drawing": "svg", "shop_drawing": "dxf", "section": "section-dxf"}.get(b.name, b.name)
            emit(stage="derive", status="running", backend=label)
            try:
                result["artifacts"][label] = b.compile(el, out).name
                emit(stage="derive", status="done", backend=label)
            except Exception as e:
                result["artifacts"][f"{label}_error"] = f"{type(e).__name__}: {e}"
                emit(stage="derive", status="failed", backend=label, message=str(e))
        # the shop-drawing backend renders a PNG preview alongside the DXF — surface it if present
        preview = out / f"{el.id}.png"
        if preview.exists():
            result["artifacts"]["drawing_preview"] = preview.name
    return result


def _variant_payload(program, el, crit) -> dict:
    """A lightweight, FILE-FREE snapshot of one exploration variant — NO backend artifacts written.

    The contact sheet ranks many first-pass candidates token-free; only the *adopted* one pays the
    backend (fab-gate) cost. So this mirrors `_assemble`'s IR/critic/mesh serialization (same critic
    shape: element_id + severity; same tessellation) but persists nothing and stays cheap to compute.
    bbox/mesh are best-effort — a half-built solid must not sink the whole sheet."""
    from geometry import GeometryService

    passed = el is not None and crit is not None and crit.passed
    payload: dict = {
        "program": program, "passed": passed,
        "id": el.id if el is not None else None,
        "type": el.type if el is not None else None,
        "bbox": None, "dims": [], "critic": [], "mesh": None, "error": None,
    }
    if el is not None:
        g = GeometryService()
        payload["dims"] = _dims(el.manifest)
        if el.geometry is not None:
            try:
                length, width, height = g.bbox(el.geometry)
                payload["bbox"] = {"length": round(length, 4), "width": round(width, 4),
                                   "height": round(height, 4)}
            except Exception:
                payload["bbox"] = None
            try:
                payload["mesh"] = g.tessellate(el.geometry)
            except Exception:
                payload["mesh"] = None
    # SAME critic serialization as _assemble — element_id + severity travel with each check so the
    # contact sheet can paint Ambient Correctness on every thumbnail.
    payload["critic"] = [
        {"check": c.check, "status": c.status.value, "message": c.message,
         "element_id": getattr(c, "element_id", None),
         "severity": getattr(getattr(c, "severity", None), "name", "ERROR").lower()}
        for c in (crit.checks if crit else [])
    ]
    return payload


def explore_to_result(prompt: str, n: int = 3, *, out: Optional[Path] = None) -> dict:
    """Generate `n` INDEPENDENT first-pass variants of a prompt and rank them by the deterministic
    critic — the exploration contact sheet (token-free to adopt; only generation costs tokens).

    Each variant is a single codegen call → execute → verify (rounds=0, NO repair). They are ranked
    by `loop._weighted_failures` ascending (fewer/lighter critic failures first; build-failures last)
    and assigned `rank` 1..n. No artifacts are written here — adoption (`adopt_to_result`) pays that
    cost for the one variant the user picks. `out` is accepted for API symmetry but unused."""
    from agent.loop import Brief, execute, generate, verify
    from agent.loop import _weighted_failures

    count = max(1, min(6, int(n)))
    brief = Brief(prompt=prompt)
    variants = []
    for _ in range(count):
        program = generate(brief)
        el, err = execute(program)
        crit = verify(el, brief) if el is not None else None
        payload = _variant_payload(program, el, crit)
        if err:
            payload["error"] = err
        variants.append((payload, crit))

    variants.sort(key=lambda v: _weighted_failures(v[1]))
    ranked = []
    for rank, (payload, _crit) in enumerate(variants, start=1):
        payload["rank"] = rank
        ranked.append(payload)
    return {"prompt": prompt, "variants": ranked}


def adopt_to_result(program: str, *, out: Optional[Path] = None) -> dict:
    """Adopt an explored variant: re-execute its program and run the FULL `_assemble` (artifacts + the
    fab gate). NO generation happens — adoption is token-free; the program text already exists from the
    contact sheet. References are by program lineage, never a stale kernel handle ([H2])."""
    from agent.loop import Brief, LoopResult, execute, verify

    out = Path(out) if out is not None else OUT
    out.mkdir(parents=True, exist_ok=True)
    el, err = execute(program)
    crit = verify(el, Brief(prompt="")) if el is not None else None
    passed = el is not None and crit is not None and crit.passed
    res = LoopResult(program, el, crit, passed, 0, err)
    result = _assemble(res, out)
    result["adopted"] = True
    return result


def section_to_result(program: str, *, axis: Optional[str] = None,
                      offset: Optional[float] = None) -> dict:
    """A live, re-promptable cut plane (R33). Execute the program token-free, slice the solid at the
    section plane, tessellate the KEPT half, and return a render-ready section mesh — no LLM, no
    backends, no files. The plane: explicit `axis`/`offset` if given (a slider/gizmo drag); else a
    declared {kind:'section'} feature on the element; else the centroidal-longitudinal default. This
    is the same plane the section DRAWING backend (R30) would draw, so the 3D slice and the DXF agree.
    """
    from agent.loop import execute
    from geometry import GeometryService

    el, err = execute(program)
    if err or el is None or el.geometry is None:
        return {"ok": False, "reason": err or "no geometry to section"}
    g = GeometryService()

    feat = next((f for f in getattr(el, "features", [])
                 if isinstance(f, dict) and f.get("kind") == "section"), None)
    if axis is None and feat is not None:
        axis = feat.get("axis")
    if offset is None and feat is not None:
        offset = feat.get("offset")
    if axis not in ("x", "y", "z"):
        axis = None                                        # ignore a bad axis → fall to the default
    ra, ro = g.default_section_plane(el.geometry, axis=axis)
    axis = axis if axis is not None else ra
    offset = float(offset) if offset is not None else ro

    try:
        kept = g.section(el.geometry, axis=axis, offset=offset, keep="-")
        mesh = g.tessellate(kept)
    except Exception as e:                                 # a degenerate plane (outside the solid) etc.
        return {"ok": False, "reason": f"{type(e).__name__}: {e}", "axis": axis, "offset": offset}
    if not mesh.get("indices"):
        return {"ok": False, "reason": "empty section (plane misses the solid)", "axis": axis, "offset": offset}

    length, width, height = g.bbox(el.geometry)
    span = {"x": (length, 0), "y": (width, 1), "z": (height, 2)}[axis][0]
    return {"ok": True, "id": el.id, "type": el.type, "axis": axis, "offset": round(offset, 4),
            "mesh": mesh, "span": round(span, 4),
            "bbox": {"length": round(length, 4), "width": round(width, 4), "height": round(height, 4)}}


def compile_to_result(prompt: str, *, candidates: int = 1, rounds: int = 2,
                      out: Optional[Path] = None, on_event=None) -> dict:
    """Compile a prompt to real artifacts and return a JSON-safe result.

    `on_event(dict)` (optional) streams the loop + derive stages for a live Activity Rail; the
    return value is identical whether or not it is supplied (the loop stays the source of truth)."""
    from agent.loop import Brief, run

    out = Path(out) if out is not None else OUT
    out.mkdir(parents=True, exist_ok=True)
    res = run(Brief(prompt=prompt), candidates=candidates, rounds=rounds, on_event=on_event)
    result = _assemble(res, out, on_event=on_event)
    result["prompt"] = prompt
    return result


def edit_to_result(program: str, instruction: str, *, param: Optional[dict] = None,
                   rounds: int = 1, out: Optional[Path] = None, allow_llm: bool = True) -> dict:
    """Re-prompt an existing program with a change, aiming for a MINIMAL diff (the editability thesis,
    S6). Returns the same shape as compile_to_result plus `diff` (+added/-removed line counts and the
    unified diff) so the UI can show that an edit is a surgical change, not a rewrite ([H2] lineage).

    When `param={name, old, new}` is supplied (a slider drag on an extent dim), a deterministic
    no-LLM fast-path is tried first; it falls through to the LLM edit if the change is ambiguous or
    doesn't verify. `result["fast"]` flags which path ran.

    `allow_llm=False` (the public demo) FORBIDS the inference fallback: if the deterministic path can't
    apply, return a clean rejection rather than exec'ing model-authored, un-gated code. Without this a
    well-formed param whose dim isn't a deterministic extent (e.g. `diameter`) would reach the LLM
    exec() path, defeating the demo's RCE gate entirely."""
    from agent.loop import edit

    out = Path(out) if out is not None else OUT
    out.mkdir(parents=True, exist_ok=True)
    if param and {"name", "old", "new"} <= set(param):
        n, o, v = param["name"], float(param["old"]), float(param["new"])
        # value-based substitute-all first (handles echoed literals); then R8 span edit for the
        # ambiguous case (a square's length == width) where substitute-all moves the wrong extent too.
        fast = _try_fast_edit(program, n, o, v, out) or _try_span_edit(program, n, o, v, out)
        if fast is not None:
            fast["instruction"] = instruction
            return fast
    if not allow_llm:   # demo: never exec model-authored code — the deterministic path didn't apply
        return {"fatal": "this change needs generation, which is disabled in the public demo. Drag a "
                         "dimension instead, or run Ludwig locally with your own AI key.",
                "instruction": instruction, "fast": False}
    res = edit(program, instruction, rounds=rounds)
    result = _assemble(res, out)
    result["instruction"] = instruction
    result["fast"] = False
    diff = list(difflib.unified_diff(program.splitlines(), res.program.splitlines(), lineterm="", n=1))
    result["diff"] = {
        "added": sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++")),
        "removed": sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---")),
        "text": "\n".join(diff),
    }
    return result


# R7: per-program FeatureGraph cache for the instant direct-manipulation path. Keyed by program text;
# the graph (+ a shared EvalCache) is recovered once by executing the program under recording(), then
# every slider tick reuses it so only the dirty subtree rebuilds — no whole-program re-exec, no LLM.
_GRAPH_CACHE: dict[str, dict] = {}


def _graph_for(program: str) -> dict:
    """{graph, el, cache} for `program`, cached by text. graph is None when the program isn't
    graph-expressible (raw-CadQuery closure, build error, or an assembly) — preview then falls back to
    text substitution. The Element is kept for its manifest/type/features when wrapping the result."""
    entry = _GRAPH_CACHE.get(program)
    if entry is not None:
        return entry
    from agent.loop import execute
    from geometry.evaluator import EvalCache, is_graph_expressible
    el, err = execute(program, record=True)
    if (err or el is None or el.graph is None or el.children
            or not is_graph_expressible(el.graph)):
        entry = {"graph": None, "el": None, "cache": None}
    else:
        entry = {"graph": el.graph, "el": el, "cache": EvalCache()}
    if len(_GRAPH_CACHE) > 64:          # bound per-process growth across many distinct edits
        _GRAPH_CACHE.clear()
    _GRAPH_CACHE[program] = entry
    return entry


def _nodes_for_dim(graph, name: str, old: float, tol: float = 1e-6) -> list[tuple[str, str]]:
    """(node_id, param) targets a slider edit on dim `name` drives: graph nodes carrying a numeric
    param `name` whose value == `old` (box extents length/width/height; a hole/anchor diameter; …).
    Matching on value mirrors the text path's substitute-all so shared edits (both holes) move together."""
    out: list[tuple[str, str]] = []
    for n in graph.nodes:
        v = n.params.get(name)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(float(v) - old) <= tol:
            out.append((n.node_id, name))
    return out


def preview_edit(program: str, name: str, old: float, new: float) -> dict:
    """Geometry-only LIVE preview for a slider drag — the direct-manipulation path.

    Fast path (R7): if the program's recorded FeatureGraph drives this dim, rebuild only the dirty
    subtree via the deterministic evaluator (set_param) — no re-exec of the whole program, no LLM.
    Otherwise fall back to substituting the literal and re-executing (the original path). Either way it
    writes NO files and runs NO backends — that is what makes it instant, so the 3D model updates
    continuously under the slider. The real `edit_to_result` (fab gate + minimal-diff) runs once, on
    release. Returns {"ok": False, ...} when the change can't be applied cleanly, so the UI keeps the
    last good mesh rather than flickering."""
    from toolkit.standards import tol_linear
    tol = max(tol_linear(), 1e-3)
    entry = _graph_for(program)
    if entry["graph"] is not None:
        nodes = _nodes_for_dim(entry["graph"], name, old)
        if nodes:
            fast = _preview_via_evaluator(entry, nodes, name, float(new), tol)
            if fast is not None:
                return fast
    return _preview_via_substitution(program, name, old, new, tol)


def _preview_via_evaluator(entry: dict, nodes, name: str, new: float, tol: float):
    """Rebuild only the dirty subtree for a slider edit and return the preview payload — or None to
    fall back. The evaluator gives geometry; dims/critic come from the recorded Element's manifest
    (with the edited dim updated) wrapped around the new handle, so Ambient Correctness repaints live."""
    from agent.loop import Brief, verify
    from geometry import GeometryService
    from geometry.evaluator import Evaluator
    from ir.elements import Element, NamedDim

    g = GeometryService()
    ev = Evaluator(entry["graph"], cache=entry["cache"])
    ev.build()                                       # warm against the shared cache (cheap when hot)
    handle, rebuilt = None, set()
    for nid, pname in nodes:
        handle, rb = ev.set_param(nid, pname, new)
        rebuilt |= rb
    try:
        length, width, height = g.bbox(handle)
        mesh = g.tessellate(handle)
    except Exception:
        return None                                  # unbuildable → fall back to substitution
    axis = _EXTENT_AXIS.get(name)
    if axis is not None and abs((length, width, height)[axis] - new) > tol:
        return None                                  # extent didn't land as expected → fall back
    base = entry["el"]
    dims = _dims(base.manifest)
    for d in dims:
        if d["name"] == name:
            d["value"] = new
    tmp = Element(id=base.id, type=base.type, name=base.name)
    tmp.geometry = handle
    tmp.manifest = [NamedDim(d["name"], d["value"], d.get("unit", "mm")) for d in dims]
    tmp.features = base.features
    crit = verify(tmp, Brief(prompt=""))
    return {"ok": True, "id": base.id, "type": base.type, "dims": dims,
            "bbox": {"length": round(length, 4), "width": round(width, 4), "height": round(height, 4)},
            "mesh": mesh, "children": [],
            "critic": [
                {"check": c.check, "status": c.status.value, "message": c.message,
                 "element_id": getattr(c, "element_id", None),
                 "severity": getattr(getattr(c, "severity", None), "name", "ERROR").lower()}
                for c in (crit.checks if crit else [])],
            "engine": "evaluator", "rebuilt": sorted(rebuilt)}


def _preview_via_substitution(program: str, name: str, old: float, new: float, tol: float) -> dict:
    """The original preview path: substitute the literal, re-execute in-process, tessellate. Handles
    everything the evaluator can't yet (raw-CadQuery closures, assemblies). Behavior unchanged."""
    new_program = _substitute_all_literals(program, old, new)
    if new_program is None:
        return {"ok": False, "reason": "literal-not-found"}
    from agent.loop import Brief, execute, verify
    el, err = execute(new_program)
    if err or el is None or el.geometry is None:
        return {"ok": False, "reason": err or "no-geometry"}
    from geometry import GeometryService
    g = GeometryService()
    try:
        length, width, height = g.bbox(el.geometry)
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    axis = _EXTENT_AXIS.get(name)  # for an extent dim, confirm the substitution drove the intended axis
    if axis is not None and abs((length, width, height)[axis] - new) > tol:
        return {"ok": False, "reason": "axis-mismatch"}
    out: dict = {"ok": True, "id": el.id, "type": el.type, "dims": _dims(el.manifest),
                 "bbox": {"length": round(length, 4), "width": round(width, 4), "height": round(height, 4)},
                 "mesh": None, "children": [], "critic": [], "engine": "substitution"}
    try:
        out["mesh"] = g.tessellate(el.geometry)
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    for c in getattr(el, "children", []) or []:  # assemblies: one selectable mesh per child, as in _assemble
        child = {"id": c.id, "type": c.type, "mesh": None}
        if c.geometry is not None:
            try:
                child["mesh"] = g.tessellate(c.geometry)
            except Exception:
                child["mesh"] = None
        out["children"].append(child)
    crit = verify(el, Brief(prompt=""))  # so Ambient Correctness repaints live (amber the moment it leaves spec)
    out["critic"] = [
        {"check": c.check, "status": c.status.value, "message": c.message,
         "element_id": getattr(c, "element_id", None),
         "severity": getattr(getattr(c, "severity", None), "name", "ERROR").lower()}
        for c in (crit.checks if crit else [])
    ]
    return out


__all__ = ["compile_to_result", "edit_to_result", "explore_to_result", "adopt_to_result",
           "section_to_result", "preview_edit", "_variant_payload", "OUT"]
