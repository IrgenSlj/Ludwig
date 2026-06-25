"""Geometry service — OCCT exact B-rep via CadQuery (BRIEF §2.3, the kernel is locked).

CadQuery is imported LAZILY so the IR/critic skeleton imports clean before the kernel is
installed (keeps --selftest/CI green). The wrapper is swappable (build123d); OCCT is not.

P0 (S2) fills these in. Today they are honest stubs that materialize BRepHandle builders.
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
            "CadQuery is not installed. The geometry kernel arrives in P0/S2: "
            "`pip install cadquery`. See BRIEF.md §4."
        ) from e
    return cq


class GeometryService:
    """Builds exact solids and answers geometric queries the critic needs.

    Every method that produces geometry returns a lazy BRepHandle, so the IR can be
    assembled and inspected without paying kernel cost until a backend or critic forces it.
    """

    def box(self, length: float, width: float, height: float) -> BRepHandle:
        def build() -> Any:
            cq = _cq()
            return cq.Workplane("XY").box(length, width, height)
        return BRepHandle(build)

    def bbox(self, handle: BRepHandle) -> tuple[float, float, float]:
        """Bounding-box extents — the dimensional critic checks these against declared dims."""
        bb = handle.solid().val().BoundingBox()
        return (bb.xlen, bb.ylen, bb.zlen)

    # P0/S2: hole(), fillet(), boolean ops. NB OCCT throws StdFail_NotDone on bad
    # fillet/boolean — the repair loop must parse that opaque failure (BRIEF §8).
    def hole(self, handle: BRepHandle, diameter: float, at, through: bool = True) -> BRepHandle:  # noqa: ARG002
        raise NotImplementedError("GeometryService.hole — P0/S2")
