"""Best-effort .glb export used by the daemon persist path.

The canonical export now lives in the Blender adapter (``adapters.engines.blender``)
since M4 — this module is the thin daemon-side wrapper that adds the env gate and the
never-raise guarantee. A missing preview must never fail a generation.
"""
from __future__ import annotations

import os
from pathlib import Path

from adapters.engines.blender.adapter import export_glb  # re-exported (canonical impl)

__all__ = ["export_glb", "maybe_export"]


def maybe_export(scene_code: str, out_glb: str | Path) -> Path | None:
    """Export a preview, or None. Skipped via ``LUDWIG_DISABLE_GLB`` or on any failure."""
    if os.environ.get("LUDWIG_DISABLE_GLB"):
        return None
    try:
        ok, _ = export_glb(scene_code, out_glb)
        return Path(out_glb) if ok else None
    except Exception:
        return None
