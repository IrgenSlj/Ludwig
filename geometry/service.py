"""Geometry service — OCCT exact B-rep via CadQuery (BRIEF §2.3, the kernel is locked).

CadQuery is imported LAZILY so the IR/critic skeleton imports clean before the kernel is
installed (keeps --selftest/CI green). The wrapper is swappable (build123d); OCCT is not.

Every geometry-producing method returns a lazy BRepHandle, so the IR can be assembled and
inspected without paying kernel cost until a backend or critic forces materialization.
"""
from __future__ import annotations

from typing import Any

from ir.elements import BRepHandle


def _cq() -> Any:
    """Import CadQuery on demand with a friendly error if the kernel isn't installed yet."""
    try:
        import cadquery as cq  # noqa: PLC0415  (lazy by design)
    except ImportError as e:  # pragma: no cover - exercised once the kernel lands
        raise RuntimeError(
            "CadQuery is not installed (the geometry kernel for P0/S2): "
            "`pip install cadquery`. See BRIEF.md §4."
        ) from e
    return cq


class GeometryService:
    """Builds exact solids and answers the geometric queries the critic needs."""

    # ---- constructors (return lazy handles) ----

    def box(self, length: float, width: float, height: float) -> BRepHandle:
        """A box centred on the origin; bbox extents are exactly (length, width, height)."""
        def build() -> Any:
            cq = _cq()
            return cq.Workplane("XY").box(length, width, height)
        return BRepHandle(build)

    def compound(self, handles) -> BRepHandle:
        """Combine several solids into one OCCT compound (for Assembly geometry)."""
        def build():
            cq = _cq()
            solids = [h.solid().val() for h in handles]
            c = cq.Compound.makeCompound(solids)
            return cq.Workplane().newObject([c])
        return BRepHandle(build)

    def hole(self, handle: BRepHandle, diameter: float, at: tuple[float, float],
             *, through: bool = True, depth: float | None = None) -> BRepHandle:
        """Drill a vertical hole of `diameter` at (x, y) measured from the top face centre.

        NB OCCT throws the opaque `StdFail_NotDone` on bad boolean/fillet geometry — the
        repair loop must parse that (BRIEF §8). For a clean through-hole in a plate it's robust.
        """
        def build() -> Any:
            wp = handle.solid()                       # a cq.Workplane
            x, y = at
            top = wp.faces(">Z").workplane(centerOption="ProjectedOrigin").pushPoints([(x, y)])
            return top.hole(diameter) if through else top.hole(diameter, depth=depth)
        return BRepHandle(build)

    # ---- queries (used by the dimensional/geometric critic and the eval harness) ----

    def bbox(self, handle: BRepHandle) -> tuple[float, float, float]:
        """Bounding-box extents (x, y, z). The dimensional critic checks these vs declared dims."""
        bb = handle.solid().val().BoundingBox()
        return (bb.xlen, bb.ylen, bb.zlen)

    def is_valid(self, handle: BRepHandle) -> bool:
        """OCCT topological validity (a coarse manifold/watertight proxy; the real panel is S4)."""
        return bool(handle.solid().val().isValid())

    def cylindrical_face_count(self, handle: BRepHandle) -> int:
        """Count cylindrical faces — for the fillet-free frozen brief set this equals hole count.
        (A full hole-topology check is S4 critic work; this is the cheap S2 gate signal.)"""
        n = 0
        for f in handle.solid().val().Faces():
            try:
                if f.geomType() == "CYLINDER":
                    n += 1
            except Exception:  # pragma: no cover - geomType can throw on exotic surfaces
                pass
        return n
