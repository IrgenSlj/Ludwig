"""Render backend — Blender headless (bpy) (BRIEF §7, P1).

Reuses the salvaged realism toolkit `backends/render_toolkit.py` (the mesh-era L_* helpers).
bpy and the toolkit are imported LAZILY (Blender is BYO; never import at module load).
The render backend hosts the DEMOTED vision critic's only domain (soft, pairwise aesthetics).
"""
from __future__ import annotations

from pathlib import Path

name = "render"
fmt = "png"
fabrication = False


# Module-level self-registration
from backends.registry import register as _register
import sys as _sys
_register(_sys.modules[__name__])


def compile(ir: object, out_dir: Path) -> Path:  # noqa: A001, ARG001
    # P1: tessellate IR solids → bpy mesh, then `from backends import render_toolkit as L`
    # for L_pbr / L_lighting / L_autocam / L_quality. Lazy import keeps the skeleton clean.
    raise NotImplementedError("render.compile — P1 (wires in backends/render_toolkit.py)")
