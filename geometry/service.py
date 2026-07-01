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

    def translate(self, handle: BRepHandle, offset: tuple[float, float, float]) -> BRepHandle:
        """Translate a solid by (dx, dy, dz) mm — the primitive for positioning parts in an assembly."""
        def build() -> Any:
            return handle.solid().translate(tuple(float(c) for c in offset))
        return BRepHandle(build)

    def hole(self, handle: BRepHandle, diameter: float, at: tuple[float, float],
             *, through: bool = True, depth: float | None = None) -> BRepHandle:
        """Drill a vertical hole of `diameter` at (x, y) measured from the top face centre.

        Returns a NEW BRepHandle that chains on the previous handle's build result. The
        previous handle is captured in the closure, so calling hole() twice on the same
        original handle creates two independent chains — each materializes the full
        history when .solid() is called. This avoids mutation of shared intermediate handles.

        NB OCCT throws the opaque `StdFail_NotDone` on bad boolean/fillet geometry — the
        repair loop must parse that (BRIEF §8). For a clean through-hole in a plate it's robust.
        """
        def build() -> Any:
            wp = handle.solid()                       # a cq.Workplane
            x, y = at
            top = wp.faces(">Z").workplane(centerOption="ProjectedOrigin").pushPoints([(x, y)])
            return top.hole(diameter) if through else top.hole(diameter, depth=depth)
        return BRepHandle(build)

    def prism(self, profile, width: float, plane: str = "XZ") -> BRepHandle:
        """Extrude a closed 2D polyline `profile` (a list of (u, v) points in `plane`) by `width` along
        the plane normal — a single solid, no booleans. Used for saw-tooth stair flights and other
        constant-section members. `profile` must be a simple (non-self-intersecting) loop; .close()
        joins the last point back to the first."""
        pts = [tuple(float(c) for c in p) for p in profile]

        def build() -> Any:
            cq = _cq()
            return cq.Workplane(plane).polyline(pts).close().extrude(float(width))
        return BRepHandle(build)

    def extrude(self, profile, depth: float, plane: str = "XY") -> BRepHandle:
        """Extrude a closed 2D polyline (a solved sketch's outer loop, in `plane`) by `depth` along the
        plane normal → a prism. The face is built from polyline().close().extrude(); a non-simple loop
        surfaces as a kernel error via execute(). This is the sketch→solid compiler (R28)."""
        pts = [tuple(float(c) for c in p) for p in profile]

        def build() -> Any:
            cq = _cq()
            return cq.Workplane(plane).polyline(pts).close().extrude(float(depth))
        return BRepHandle(build)

    def cut(self, handle: BRepHandle, box_spec) -> BRepHandle:
        """Subtract a rectangular box from a solid — the generic rect boolean for openings, slots,
        pockets. `box_spec = (length, width, height, (cx, cy, cz))`: a box of those extents centred at
        (cx, cy, cz), removed from `handle`. Returns a new lazy handle chaining on the previous build."""
        length, width, height, center = box_spec
        cx, cy, cz = (float(c) for c in center)

        def build() -> Any:
            cq = _cq()
            tool = cq.Workplane("XY").box(float(length), float(width), float(height)).translate((cx, cy, cz))
            return handle.solid().cut(tool)
        return BRepHandle(build)

    def section(self, handle: BRepHandle, *, axis: str = "x", offset: float = 0.0,
                keep: str = "-") -> BRepHandle:
        """Cut a solid with a plane perpendicular to `axis` (x|y|z) at `offset`, keeping one half
        (keep '+' = higher side, '-' = lower) — an oversized half-space box intersection, robust for
        the prismatic parts we section. StdFail_NotDone surfaces via execute()."""
        ai = {"x": 0, "y": 1, "z": 2}.get(axis, axis)

        def build() -> Any:
            cq = _cq()
            solid = handle.solid()
            big = 1e5
            sizes = [2 * big, 2 * big, 2 * big]
            sizes[ai] = big
            center = [0.0, 0.0, 0.0]
            center[ai] = offset + (big / 2 if keep in ("+", "plus", "pos") else -big / 2)
            half = cq.Workplane("XY").box(sizes[0], sizes[1], sizes[2]).translate(tuple(center))
            return solid.intersect(half)
        return BRepHandle(build)

    def section_profile(self, handle: BRepHandle, *, axis: str = "x", offset: float = 0.0) -> dict:
        """The cross-section loops at the cutting plane: {'outer': [[(u,v),…],…], 'inners': [[…],…]}
        — every face of the kept solid lying ON the plane, its outer wire(s) and any inner (hole)
        wires projected to the plane's (u, v). Through-features split the section into multiple outer
        loops; enclosed voids appear as inner loops. Best-effort; empty lists if nothing lies on the
        plane."""
        ai = {"x": 0, "y": 1, "z": 2}.get(axis, axis)
        u_ax, v_ax = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[ai]
        kept = self.section(handle, axis=axis, offset=offset, keep="+")
        solid = kept.solid()

        def uv(wire):
            return [(v.toTuple()[u_ax], v.toTuple()[v_ax]) for v in wire.Vertices()]

        outer, inners = [], []
        for f in solid.faces().vals():
            c = f.Center().toTuple()
            n = f.normalAt().toTuple()
            if abs(c[ai] - offset) < 1e-4 and abs(abs(n[ai]) - 1) < 1e-3:
                outer.append(uv(f.outerWire()))
                inners.extend(uv(w) for w in f.innerWires())
        return {"outer": outer, "inners": inners}

    def default_section_plane(self, handle: BRepHandle, axis: str | None = None) -> tuple[str, float]:
        """The default section plane: cut ⟂ the SHORTEST extent (the broadest *longitudinal* plane),
        through the bounding-box centroid — the single most informative section for a plate-like part
        (it reveals through-holes as voids). Pass `axis` to fix the cut axis and get its centroid.
        Shared by the section drawing backend (R30) and the live cut (R33) so both agree on the plane."""
        bb = handle.solid().val().BoundingBox()
        spans = {"x": bb.xlen, "y": bb.ylen, "z": bb.zlen}
        ax = axis or min(spans, key=spans.get)
        ctr = {"x": (bb.xmin + bb.xmax) / 2, "y": (bb.ymin + bb.ymax) / 2, "z": (bb.zmin + bb.zmax) / 2}
        return ax, ctr[ax]

    @staticmethod
    def loop_area(loop) -> float:
        """Shoelace area (mm²) of a closed (u, v) polygon loop. |signed area|; 0 for < 3 points."""
        n = len(loop)
        if n < 3:
            return 0.0
        a = 0.0
        for i in range(n):
            x1, y1 = loop[i]
            x2, y2 = loop[(i + 1) % n]
            a += x1 * y2 - x2 * y1
        return abs(a) / 2.0

    # ---- queries (used by the dimensional/geometric critic and the eval harness) ----

    def volume(self, handle: BRepHandle) -> float:
        """Solid volume (mm³) — the dimensional/manufacturing critic uses it to confirm a void actually
        removed material."""
        return float(handle.solid().val().Volume())


    def bbox(self, handle: BRepHandle) -> tuple[float, float, float]:
        """Bounding-box extents (x, y, z). The dimensional critic checks these vs declared dims."""
        bb = handle.solid().val().BoundingBox()
        return (bb.xlen, bb.ylen, bb.zlen)

    def tessellate(self, handle: BRepHandle, tolerance: float = 0.1,
                   angular_tolerance: float = 0.3) -> dict:
        """Triangulate the exact B-rep into a render mesh for the web viewport (the 3D Stage).

        Returns flat arrays `{positions:[x,y,z,...], indices:[i,j,k,...], center:[cx,cy,cz], radius}`
        the browser builds a three.js BufferGeometry from — the *actual* compiled solid, not a
        primitive. This is a derived projection (like STEP/SVG), never the source of truth.
        """
        shape = handle.solid().val()
        verts, tris = shape.tessellate(tolerance, angular_tolerance)
        positions: list[float] = []
        for v in verts:
            x, y, z = v.toTuple()
            positions.extend((x, y, z))
        indices: list[int] = []
        for t in tris:
            indices.extend((t[0], t[1], t[2]))
        bb = shape.BoundingBox()
        center = [(bb.xmin + bb.xmax) / 2, (bb.ymin + bb.ymax) / 2, (bb.zmin + bb.zmax) / 2]
        radius = max(bb.xlen, bb.ylen, bb.zlen)
        return {"positions": positions, "indices": indices, "center": center, "radius": radius}

    def bbox_center(self, handle: BRepHandle) -> tuple[float, float, float]:
        """Centre of the bounding box (x, y, z) — where a backend places a representative massing."""
        bb = handle.solid().val().BoundingBox()
        return ((bb.xmin + bb.xmax) / 2, (bb.ymin + bb.ymax) / 2, (bb.zmin + bb.zmax) / 2)

    def is_valid(self, handle: BRepHandle) -> bool:
        """OCCT topological validity (a coarse manifold/watertight proxy; the real panel is S4)."""
        return bool(handle.solid().val().isValid())

    def min_wall_thickness(self, handle: BRepHandle) -> float:
        """Estimate minimum wall thickness via face-pair distance (research-grade, P1).

        Computes the minimum distance between all non-adjacent face pairs using OCCT's
        BRepExtrema_DistShapeShape. Adjacent faces (distance < 1 μm) are excluded.
        This is a proxy for true min-wall analysis (medial surface / offset-based) which
        is deferred to P2 when a brief demands it.

        Returns 0.0 for degenerate or single-face shapes.
        """
        from cadquery.occ_impl.shapes import BRepExtrema_DistShapeShape  # noqa: PLC0415

        shape = handle.solid().val()
        faces = list(shape.Faces())
        if len(faces) < 2:
            return 0.0
        min_d = float("inf")
        for i, f1 in enumerate(faces):
            for f2 in faces[i + 1:]:
                extrema = BRepExtrema_DistShapeShape(f1.wrapped, f2.wrapped)
                if extrema.IsDone():
                    d = extrema.Value()
                    if 1e-3 < d < min_d:  # skip adjacent faces (distance ≈ 0)
                        min_d = d
        return min_d if min_d != float("inf") else 0.0

    def cylindrical_face_centers(self, handle: BRepHandle) -> list[tuple[float, float]]:
        """The (x, y) axis centres of every cylindrical face — hole/bore positions in plan. The
        deterministic acceptance signal for a hole-position edit (R13): confirm a hole actually landed
        at the new centre, the way bbox extents gate an extent edit. Deduped to ~0.1 mm."""
        centers: list[tuple[float, float]] = []
        for f in handle.solid().val().Faces():
            try:
                if f.geomType() == "CYLINDER":
                    c = f.Center().toTuple()
                    xy = (round(c[0], 3), round(c[1], 3))
                    if not any(abs(xy[0] - e[0]) < 0.1 and abs(xy[1] - e[1]) < 0.1 for e in centers):
                        centers.append(xy)
            except Exception:  # pragma: no cover - geomType can throw on exotic surfaces
                pass
        return centers

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
