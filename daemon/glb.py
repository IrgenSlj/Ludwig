"""Export a generated scene to a web-viewable ``.glb`` (M2).

Reuses ``ludwig``'s Blender invocation pattern (toolkit prepended, headless
``--background --python``) without modifying ``ludwig.py``: we build the scene the
same way ``render()`` does, then export glTF-binary instead of rendering. This is the
interactive-preview surface — the thing image generators cannot do (BRIEF.md §6).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import ludwig

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


def export_glb(scene_code: str, out_glb: str | Path, *, timeout: int = 300) -> tuple[bool, str]:
    """Run the scene in headless Blender and export a .glb. Returns (ok, log)."""
    out_glb = str(out_glb)
    if not ludwig.BLENDER or not os.path.exists(ludwig.BLENDER):
        return False, "Blender not found"

    header = f"OUT_GLB = {out_glb!r}\n"
    full = f"{ludwig.BLENDER_LIB}\n\n{header}\n{scene_code}\n{_EXPORT_FOOTER}"
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


def maybe_export(scene_code: str, out_glb: str | Path) -> Path | None:
    """Best-effort export used in the persist path. Returns the path or None.

    Skipped when ``LUDWIG_DISABLE_GLB`` is set (daemon wiring tests) or Blender is
    unavailable. Never raises — a missing preview must not fail a generation.
    """
    if os.environ.get("LUDWIG_DISABLE_GLB"):
        return None
    try:
        ok, _ = export_glb(scene_code, out_glb)
        return Path(out_glb) if ok else None
    except Exception:
        return None
