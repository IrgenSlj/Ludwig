"""compile_to_result / edit_to_result — the real compile + edit paths, as serializable data.

This is the seam the web UI binds to. It runs the genuine loop (generate/edit → execute → critic →
repair) and the genuine backends (STEP/IFC/SVG/mesh) — exactly what `cli.py` does — and returns a
plain dict so a browser, the CLI, or a test can all consume the same truth. No geometry is faked; the
prototype's timer-mock is replaced by this. The loop stays the source of truth (BRIEF §5); the web
server is just another *frontend*, like the CLI — adding it does not touch the loop ([H4]).
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Optional

OUT = Path("out")

# extent dims a slider can tweak deterministically, mapped to their bbox axis (x,y,z)
_EXTENT_AXIS = {"length": 0, "width": 1, "thickness": 1, "height": 2}


def _dims(manifest) -> list[dict]:
    """Serialize a manifest to JSON, deduped by name (last value wins). Live codegen sometimes
    register_dim's the same extent twice; the UI should show each named dim once."""
    seen: dict[str, dict] = {}
    for d in manifest:
        seen[d.name] = {"name": d.name, "value": d.value, "unit": d.unit}
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


def _try_fast_edit(program: str, name: str, old: float, new: float, out: Path) -> Optional[dict]:
    """Deterministic, no-LLM parametric tweak for a single extent dim. Substitute the literal,
    re-execute, and ACCEPT only if the intended axis now measures `new` and the solid is valid/
    all-pass — otherwise return None and let the caller fall back to the (correct, slower) LLM edit.
    The LLM stays the backstop; this just makes the common numeric-slider case instant."""
    axis = _EXTENT_AXIS.get(name)
    if axis is None:
        return None
    new_program = _substitute_unique_literal(program, old, new)
    if new_program is None:
        return None
    from agent.loop import Brief, LoopResult, execute, verify
    el, err = execute(new_program)
    if err or el is None:
        return None
    from geometry import GeometryService
    from toolkit.standards import tol_linear
    if abs(GeometryService().bbox(el.geometry)[axis] - new) > max(tol_linear(), 1e-3):
        return None  # the literal we changed didn't drive this axis as intended → fall back
    crit = verify(el, Brief(prompt=""))
    if not crit.passed:
        return None
    res = LoopResult(new_program, el, crit, True, 0, None)
    result = _assemble(res, out)
    diff = list(difflib.unified_diff(program.splitlines(), new_program.splitlines(), lineterm="", n=1))
    result["diff"] = {"added": 1, "removed": 1, "text": "\n".join(diff)}
    result["fast"] = True
    return result


def _assemble(res, out: Path) -> dict:
    """Turn a LoopResult into a JSON-safe dict: IR stats, critic, render mesh, persisted artifacts.

    The fabrication gate holds — STEP/IFC are written only when the critic is all-pass (no fab file
    on a failing critic, BRIEF §5). The SVG drawing and the viewer mesh are best-effort, never block.
    """
    from geometry import GeometryService

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
    result["critic"] = [
        {"check": c.check, "status": c.status.value, "message": c.message}
        for c in (res.critique.checks if res.critique else [])
    ]

    recipe = out / f"{el.id}.py"
    recipe.write_text(res.program + "\n")
    result["artifacts"]["recipe"] = recipe.name
    if res.passed:
        from backends import all as all_backends
        for b in all_backends():
            label = {"drawing": "svg"}.get(b.name, b.name)
            try:
                result["artifacts"][label] = b.compile(el, out).name
            except Exception as e:
                result["artifacts"][f"{label}_error"] = f"{type(e).__name__}: {e}"
    return result


def compile_to_result(prompt: str, *, candidates: int = 1, rounds: int = 2,
                      out: Optional[Path] = None) -> dict:
    """Compile a prompt to real artifacts and return a JSON-safe result."""
    from agent.loop import Brief, run

    out = Path(out) if out is not None else OUT
    out.mkdir(parents=True, exist_ok=True)
    res = run(Brief(prompt=prompt), candidates=candidates, rounds=rounds)
    result = _assemble(res, out)
    result["prompt"] = prompt
    return result


def edit_to_result(program: str, instruction: str, *, param: Optional[dict] = None,
                   rounds: int = 1, out: Optional[Path] = None) -> dict:
    """Re-prompt an existing program with a change, aiming for a MINIMAL diff (the editability thesis,
    S6). Returns the same shape as compile_to_result plus `diff` (+added/-removed line counts and the
    unified diff) so the UI can show that an edit is a surgical change, not a rewrite ([H2] lineage).

    When `param={name, old, new}` is supplied (a slider drag on an extent dim), a deterministic
    no-LLM fast-path is tried first; it falls through to the LLM edit if the change is ambiguous or
    doesn't verify. `result["fast"]` flags which path ran."""
    from agent.loop import edit

    out = Path(out) if out is not None else OUT
    out.mkdir(parents=True, exist_ok=True)
    if param and {"name", "old", "new"} <= set(param):
        fast = _try_fast_edit(program, param["name"], float(param["old"]), float(param["new"]), out)
        if fast is not None:
            fast["instruction"] = instruction
            return fast
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


__all__ = ["compile_to_result", "edit_to_result", "OUT"]
