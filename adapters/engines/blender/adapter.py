"""Blender engine adapter (M4) — wraps ludwig's headless render + a glTF export.

This is the first ``ToolAdapter``. It does NOT reimplement the loop or the toolkit —
it delegates rendering to ``ludwig.render`` and adds a ``.glb`` export using the same
Blender invocation pattern. ``ludwig.py`` stays unchanged.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import ludwig

from core.models import Caps, RunResult

_EXPORT_FOOTER = """
import bpy
def _export():
    bpy.ops.export_scene.gltf(filepath=OUT_GLB, export_format='GLB')
try:
    _export()
except Exception:
    import addon_utils
    addon_utils.enable('io_scene_gltf2')
    _export()
"""

_TOOLKIT_REFERENCE = (
    "Blender Python. Call the prepended Ludwig toolkit instead of hand-rolling: "
    "L_pbr(name,color,kind) for materials (wood/fabric/ceramic/metal/glass/leather/…), "
    "L_lighting(mood) and L_studio_lights()+L_backdrop() for light rigs, "
    "L_autocam(az,el) to auto-fit the subject, L_seat(*objs) to ground it, "
    "L_bevel/L_apply for clean edges."
)


def export_glb(scene_code: str, out_glb: str | Path, *, timeout: int = 300) -> tuple[bool, str]:
    """Run the scene in headless Blender and export glTF-binary. Returns (ok, log)."""
    out_glb = str(out_glb)
    if not ludwig.BLENDER or not os.path.exists(ludwig.BLENDER):
        return False, "Blender not found"
    full = f"{ludwig.BLENDER_LIB}\n\nOUT_GLB = {out_glb!r}\n\n{scene_code}\n{_EXPORT_FOOTER}"
    try:
        os.unlink(out_glb)
    except FileNotFoundError:
        pass
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(full)
        script_path = f.name
    try:
        proc = subprocess.run(
            [ludwig.BLENDER, "--background", "--python", script_path],
            capture_output=True, text=True, timeout=timeout,
        )
        log = proc.stdout + "\n" + proc.stderr
        ok = os.path.exists(out_glb) and os.path.getsize(out_glb) > 0
        return ok, log
    except subprocess.TimeoutExpired:
        return False, f"glb export timed out after {timeout}s"
    finally:
        os.unlink(script_path)


class BlenderAdapter:
    name = "blender"
    language = "python"

    def capabilities(self) -> Caps:
        return Caps(mesh=True, outputs=("png", "glb"),
                    tags=frozenset({"mesh", "render", "image"}))

    def toolkit_reference(self) -> str:
        return _TOOLKIT_REFERENCE

    def run(self, program: str, project_dir: Path) -> RunResult:
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        png = project_dir / "render.png"
        ok, log = ludwig.render(program, str(png))
        glb_path = None
        if ok:
            cand = project_dir / "preview.glb"
            g_ok, _ = export_glb(program, cand)
            glb_path = str(cand) if g_ok else None
        return RunResult(
            code=program, ok=ok,
            renders=[str(png)] if ok else [],
            preview=glb_path, stdout=log,
            error=None if ok else ludwig._blender_error(log),
        )

    def preview(self, result: RunResult) -> str | None:
        return result.preview
