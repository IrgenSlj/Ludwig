"""compile_to_result / edit_to_result — the real compile + edit paths, as serializable data.

This is the seam the web UI binds to. It runs the genuine loop (generate/edit → execute → critic →
repair) and the genuine backends (STEP/IFC/SVG/mesh) — exactly what `cli.py` does — and returns a
plain dict so a browser, the CLI, or a test can all consume the same truth. No geometry is faked; the
prototype's timer-mock is replaced by this. The loop stays the source of truth (BRIEF §5); the web
server is just another *frontend*, like the CLI — adding it does not touch the loop ([H4]).
"""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Optional

OUT = Path("out")


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
        "bbox": None, "dims": [], "critic": [], "mesh": None, "artifacts": {},
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
    result["dims"] = [{"name": d.name, "value": d.value, "unit": d.unit} for d in el.manifest]
    result["critic"] = [
        {"check": c.check, "status": c.status.value, "message": c.message}
        for c in (res.critique.checks if res.critique else [])
    ]

    recipe = out / f"{el.id}.py"
    recipe.write_text(res.program + "\n")
    result["artifacts"]["recipe"] = recipe.name
    if res.passed:
        from importlib import import_module
        from backends import step as step_backend
        result["artifacts"]["step"] = step_backend.compile(el, out).name
        for label, mod in (("ifc", "ifc"), ("svg", "drawing")):
            try:
                result["artifacts"][label] = import_module(f"backends.{mod}").compile(el, out).name
            except Exception as e:  # IFC/drawing are best-effort; never sink the compile
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


def edit_to_result(program: str, instruction: str, *, rounds: int = 1,
                   out: Optional[Path] = None) -> dict:
    """Re-prompt an existing program with a change, aiming for a MINIMAL diff (the editability thesis,
    S6). Returns the same shape as compile_to_result plus `diff` (+added/-removed line counts and the
    unified diff) so the UI can show that an edit is a surgical change, not a rewrite ([H2] lineage)."""
    from agent.loop import edit

    out = Path(out) if out is not None else OUT
    out.mkdir(parents=True, exist_ok=True)
    res = edit(program, instruction, rounds=rounds)
    result = _assemble(res, out)
    result["instruction"] = instruction
    diff = list(difflib.unified_diff(program.splitlines(), res.program.splitlines(), lineterm="", n=1))
    result["diff"] = {
        "added": sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++")),
        "removed": sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---")),
        "text": "\n".join(diff),
    }
    return result


__all__ = ["compile_to_result", "edit_to_result", "OUT"]
