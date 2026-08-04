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

    def cylinder(self, diameter: float, height: float) -> BRepHandle:
        """A cylinder centred on the origin, axis along +Z; bbox extents are (diameter, diameter, height).
        The robust round primitive for flanges/shafts/washers — no boolean, so it never StdFails."""
        def build() -> Any:
            cq = _cq()
            return cq.Workplane("XY").cylinder(float(height), float(diameter) / 2.0)
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

    def fillet(self, handle: BRepHandle, radius: float, *, faces: str = ">Z") -> BRepHandle:
        """Round the edges of the selected face(s) by `radius` mm (default the top +Z face) — the common
        deburr/edge-break. StdFail_NotDone surfaces via execute() if the radius exceeds the geometry."""
        def build() -> Any:
            return handle.solid().faces(faces).fillet(float(radius))
        return BRepHandle(build)

    def chamfer(self, handle: BRepHandle, distance: float, *, selector: str = "bore") -> BRepHandle:
        """Bevel edges by `distance` mm. selector='bore' chamfers circular (hole/bore) edges; 'top'
        chamfers the top-face edges. Lead-ins for fasteners / bores."""
        def build() -> Any:
            wp = handle.solid()
            if selector == "bore":
                return wp.edges("%Circle").chamfer(float(distance))
            return wp.faces(">Z").edges().chamfer(float(distance))
        return BRepHandle(build)

    def slot(self, handle: BRepHandle, width: float, length: float,
             at: tuple[float, float] = (0.0, 0.0)) -> BRepHandle:
        """Cut a rectangular through-slot `length`×`width` mm centred at (x, y) on the top face — a
        generic rectangular cutout (cable slot, adjustment slot)."""
        x, y = at

        def build() -> Any:
            return (handle.solid().faces(">Z").workplane()
                    .center(float(x), float(y)).rect(float(length), float(width)).cutThruAll())
        return BRepHandle(build)

    def counterbore(self, handle: BRepHandle, through_dia: float, cbore_dia: float,
                    cbore_depth: float, at: tuple[float, float]) -> BRepHandle:
        """A counterbored hole at (x, y): a `through_dia` through-hole plus a `cbore_dia` recess
        `cbore_depth` mm deep from the top face — a socket-head cap-screw pocket."""
        x, y = at

        def build() -> Any:
            cq = _cq()
            wp = handle.solid()
            h = wp.val().BoundingBox().zlen
            through = cq.Workplane("XY").transformed(offset=(x, y, -h / 2)).circle(float(through_dia) / 2).extrude(h)
            recess = cq.Workplane("XY").transformed(offset=(x, y, h / 2)).circle(float(cbore_dia) / 2).extrude(-float(cbore_depth))
            return wp.cut(through).cut(recess)
        return BRepHandle(build)

    def section(self, handle: BRepHandle, *, axis: str = "x", offset: float = 0.0,
                keep: str = "-") -> BRepHandle:
        """Cut a solid with a plane perpendicular to `axis` (x|y|z) at `offset`, keeping one half
        (keep '+' = higher side, '-' = lower) — an oversized half-space box intersection, robust for
        the prismatic parts we section. StdFail_NotDone surfaces via execute()."""
        _axis_idx = {"x": 0, "y": 1, "z": 2}
        if axis not in _axis_idx:
            raise ValueError(f"section axis must be 'x', 'y', or 'z', got {axis!r}")
        ai = _axis_idx[axis]

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
        _axis_idx = {"x": 0, "y": 1, "z": 2}
        if axis not in _axis_idx:
            raise ValueError(f"section_profile axis must be 'x', 'y', or 'z', got {axis!r}")
        ai = _axis_idx[axis]
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

    @staticmethod
    def _parts(handle: BRepHandle) -> list:
        """The handle's shape as a list of PAIRWISE NON-OVERLAPPING solids.

        Fusing first is what buys the guarantee: OCCT's fuse merges any genuinely overlapping
        solids into one, so whatever solids survive are disjoint or merely touching. That makes
        `Σ Vol(part)` the true volume and makes the part-wise intersection below exact.

        Measured, not assumed (B1): BenchCAD's `ball_knob` is `sphere(12.5)` unioned with a stem
        cylinder that is TANGENT to it (they meet at the south pole, a single point), so the union
        is legitimately a 2-solid compound. `Compound.intersect(Compound)` then returned only one
        pair's common — scoring the shape IoU **0.247 against itself**. Voxel IoU (what BenchCAD
        publishes) never hits this, because rasterizing a compound is implicitly a union.
        """
        shape = handle.solid().val()
        solids = shape.Solids()
        if len(solids) <= 1:
            return [shape]
        try:
            fused = solids[0].fuse(*solids[1:]).clean()
        except Exception:
            return solids                      # a fuse OCCT won't complete: treat as already disjoint
        return fused.Solids() or [fused]

    @staticmethod
    def _bb_disjoint(x, y) -> bool:
        """True when two shapes' bounding boxes cannot overlap — lets the pair-wise intersection
        skip the boolean entirely (faster, and it avoids asking OCCT for an empty common)."""
        p, q = x.BoundingBox(), y.BoundingBox()
        return (p.xmax < q.xmin or q.xmax < p.xmin or p.ymax < q.ymin
                or q.ymax < p.ymin or p.zmax < q.zmin or q.zmax < p.zmin)

    def iou(self, a: BRepHandle, b: BRepHandle) -> float:
        """Exact volumetric IoU of two solids: Vol(A∩B) / Vol(A∪B), via OCCT booleans (B1).

        This is the geometric grade for the BenchCAD edit benchmark. It is computed on the **exact**
        B-rep — not a voxel grid — so it is deterministic and has no resolution error. NB BenchCAD's
        published numbers use a 256³ voxel IoU, so absolute values are close but not identical; the
        difference is stated wherever a number is reported (docs/BENCH_PLAN.md).

        With A = ⋃aᵢ and B = ⋃bⱼ over non-overlapping parts (see `_parts`), the pieces aᵢ∩bⱼ are
        themselves pairwise non-overlapping, so `Vol(A∩B) = Σᵢⱼ Vol(aᵢ∩bⱼ)` exactly — no
        inclusion–exclusion, and no reliance on OCCT doing the right thing with compound arguments.

        Both solids must share a coordinate frame (BenchCAD's orig/gt variants do). Raises whatever
        OCCT raises on a boolean it cannot complete — the caller decides whether that is a grading
        failure or a hard error.
        """
        pa, pb = self._parts(a), self._parts(b)
        va = sum(float(s.Volume()) for s in pa)
        vb = sum(float(s.Volume()) for s in pb)
        if va <= 0.0 or vb <= 0.0:
            return 0.0
        inter = 0.0
        for x in pa:
            for y in pb:
                if self._bb_disjoint(x, y):
                    continue
                inter += float(x.intersect(y).Volume())
        union = va + vb - inter
        return 0.0 if union <= 0.0 else max(0.0, min(1.0, inter / union))

    def import_step(self, source) -> BRepHandle:
        """Read a STEP file Ludwig did NOT author into a lazy handle (B2).

        `source` is a path (str/Path) or raw STEP bytes. Bytes are written to a temp file because
        OCCT's reader is path-based. The result carries no manifest and no feature graph — it is
        geometry only, which is exactly why the dimensional critic must report N/A on it rather
        than vacuum-pass (see critic/dimensional.py).
        """
        def build() -> Any:
            cq = _cq()
            import os
            import tempfile
            path = source
            tmp = None
            if isinstance(source, (bytes, bytearray)):
                fd, tmp = tempfile.mkstemp(suffix=".step")
                with os.fdopen(fd, "wb") as fh:
                    fh.write(source)
                path = tmp
            try:
                return cq.importers.importStep(str(path))
            finally:
                if tmp:
                    os.unlink(tmp)
        return BRepHandle(build)

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

    def print_mesh_stats(self, handle: BRepHandle, *, tolerance: float = 0.1) -> dict:
        """Print-orientation mesh analysis for the printability critic (A7); build direction +Z. From the
        tessellated solid returns:
          - `max_overhang_deg`: the steepest DOWNWARD-facing surface angle from vertical, EXCLUDING faces
            resting on the build plate (a bed face is support-free). 0 = only vertical/upward faces;
            90 = a flat ceiling needing full support.
          - `bed_contact_mm2`: total area of triangles lying on the bed (z ≈ z_min) — the first-layer footprint.
        Triangle normals come from the winding (OCCT tessellation is outward-wound for a valid solid); a
        downward normal is one whose unit z < 0.
        """
        import math

        m = self.tessellate(handle, tolerance)
        pos, idx = m["positions"], m["indices"]
        if not idx:
            return {"max_overhang_deg": 0.0, "bed_contact_mm2": 0.0}
        zs = pos[2::3]
        z_min, z_max = min(zs), max(zs)
        bed_tol = max(1e-4, (z_max - z_min) * 1e-4)     # relative "on the bed" tolerance
        max_overhang, bed_area = 0.0, 0.0
        for i in range(0, len(idx), 3):
            a, b, c = idx[i] * 3, idx[i + 1] * 3, idx[i + 2] * 3
            p0, p1, p2 = pos[a:a + 3], pos[b:b + 3], pos[c:c + 3]
            ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx   # outward normal × 2·area
            mag = math.sqrt(nx * nx + ny * ny + nz * nz)
            if mag < 1e-12:
                continue
            nzu = nz / mag                               # unit normal z
            on_bed = all(p[2] - z_min <= bed_tol for p in (p0, p1, p2))
            if on_bed and nzu < -0.5:                    # a downward face on the plate = bed contact
                bed_area += 0.5 * mag
            elif nzu < 0.0:                              # a downward face off the plate = an overhang
                overhang = math.degrees(math.asin(min(1.0, -nzu)))
                max_overhang = max(max_overhang, overhang)
        return {"max_overhang_deg": max_overhang, "bed_contact_mm2": bed_area}

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

    def _cylindrical_faces(self, handle: BRepHandle) -> list:
        """Return every cylindrical face from the solid (shared inner helper for center/count queries)."""
        faces = []
        for f in handle.solid().val().Faces():
            try:
                if f.geomType() == "CYLINDER":
                    faces.append(f)
            except Exception:  # pragma: no cover - geomType can throw on exotic surfaces
                pass
        return faces

    def cylindrical_face_centers(self, handle: BRepHandle) -> list[tuple[float, float]]:
        """The (x, y) axis centres of every cylindrical face — hole/bore positions in plan. The
        deterministic acceptance signal for a hole-position edit (R13): confirm a hole actually landed
        at the new centre, the way bbox extents gate an extent edit. Deduped to ~0.1 mm."""
        centers: list[tuple[float, float]] = []
        for f in self._cylindrical_faces(handle):
            c = f.Center().toTuple()
            xy = (round(c[0], 3), round(c[1], 3))
            if not any(abs(xy[0] - e[0]) < 0.1 and abs(xy[1] - e[1]) < 0.1 for e in centers):
                centers.append(xy)
        return centers

    def cylindrical_face_count(self, handle: BRepHandle) -> int:
        """Count cylindrical faces — for the fillet-free frozen brief set this equals hole count.
        (A full hole-topology check is S4 critic work; this is the cheap S2 gate signal.)"""
        return len(self._cylindrical_faces(handle))
