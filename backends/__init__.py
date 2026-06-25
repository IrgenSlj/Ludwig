"""backends — derived projections of the IR (STEP/IFC/drawing/render/present). See BRIEF §2.4.

NB: render_toolkit imports bpy at module load (mesh-era code); it is NOT imported here, only
lazily by backends.render at P1, so the skeleton imports clean without Blender installed.
"""
from backends.base import Backend

__all__ = ["Backend"]
