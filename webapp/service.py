"""compile_to_result — the ONE real compile path, returned as serializable data.

This is the seam the web UI binds to. It runs the genuine loop (generate → execute → critic →
repair) and the genuine backends (STEP/IFC/SVG) — exactly what `cli.py` does — and returns a plain
dict so a browser, the CLI, or a test can all consume the same truth. No geometry is faked here; the
prototype's timer-mock is replaced by this. The loop stays the source of truth (BRIEF §5); the web
server is just another *frontend*, like the CLI — adding it does not touch the loop ([H4]).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

OUT = Path("out")


def compile_to_result(prompt: str, *, candidates: int = 1, rounds: int = 2,
                      out: Optional[Path] = None) -> dict:
    """Compile a prompt to real artifacts and return a JSON-safe result.

    Mirrors cli.compile_prompt's pipeline but returns data instead of printing. The fabrication
    gate holds: STEP/IFC are only written when the critic is all-pass (no fab file on a failing
    critic, BRIEF §5). The SVG drawing is best-effort and never blocks.
    """
    from agent.loop import Brief, run
    from geometry import GeometryService

    out = Path(out) if out is not None else OUT
    out.mkdir(parents=True, exist_ok=True)

    res = run(Brief(prompt=prompt), candidates=candidates, rounds=rounds)
    result: dict = {
        "prompt": prompt,
        "program": res.program,
        "rounds": res.rounds,
        "passed": res.passed,
        "error": res.error,
        "id": res.ir.id if res.ir is not None else None,
        "type": res.ir.type if res.ir is not None else None,
        "bbox": None,
        "dims": [],
        "critic": [],
        "artifacts": {},
    }
    if res.ir is None:
        return result

    el = res.ir
    if el.geometry is not None:
        g = GeometryService()
        length, width, height = g.bbox(el.geometry)
        result["bbox"] = {"length": round(length, 4), "width": round(width, 4), "height": round(height, 4)}
        try:  # the 3D render mesh for the Stage viewport — best-effort, never sinks the compile
            result["mesh"] = g.tessellate(el.geometry)
        except Exception as e:
            result["mesh_error"] = f"{type(e).__name__}: {e}"
    result["dims"] = [{"name": d.name, "value": d.value, "unit": d.unit} for d in el.manifest]
    result["critic"] = [
        {"check": c.check, "status": c.status.value, "message": c.message}
        for c in (res.critique.checks if res.critique else [])
    ]

    # Persist the recipe always; gate the fabrication deliverables on the critic.
    recipe = out / f"{el.id}.py"
    recipe.write_text(res.program + "\n")
    result["artifacts"]["recipe"] = recipe.name

    if res.passed:
        from backends import step as step_backend
        result["artifacts"]["step"] = step_backend.compile(el, out).name
        for label, mod in (("ifc", "ifc"), ("svg", "drawing")):
            try:
                from importlib import import_module
                result["artifacts"][label] = import_module(f"backends.{mod}").compile(el, out).name
            except Exception as e:  # IFC/drawing are best-effort; never sink the compile
                result["artifacts"][f"{label}_error"] = f"{type(e).__name__}: {e}"
    return result


__all__ = ["compile_to_result", "OUT"]
