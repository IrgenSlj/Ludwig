"""IFC backend — the BIM deliverable (BRIEF §7, P1/S9).

IfcOpenShell authoring via the low-level `create_entity` API (stable across versions; the high-level
`ifcopenshell.api` churns — see docs/FINDINGS research). The IR's `type` maps to an IFC class via
`standards.yaml: ifc_map`. The body is an `IfcExtrudedAreaSolid` of the element's bounding box.

Fidelity note (inherent to IFC, not a bug): IFC carries the semantic element + a representative massing
solid; the *exact* geometry (holes, pockets) stays in the STEP deliverable. Full IFC4precast property
sets are a later refinement. Imported lazily.
"""
from __future__ import annotations

from pathlib import Path

name = "ifc"
fmt = "ifc"
fabrication = True


def compile(ir, out_dir) -> Path:  # noqa: A001 - matches the Backend protocol
    import ifcopenshell
    import ifcopenshell.guid as guid

    from geometry import GeometryService
    from toolkit.standards import load

    if ir.geometry is None:
        raise ValueError(f"element {ir.id!r} has no geometry to export")
    ifc_class = load().get("ifc_map", {}).get(ir.type, "IfcBuildingElementProxy")
    length, width, height = GeometryService().bbox(ir.geometry)

    f = ifcopenshell.file(schema="IFC4")

    def gid() -> str:
        return guid.new()

    def point(coords):
        return f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(c) for c in coords))

    def placement(rel_to=None):
        axis2 = f.create_entity("IfcAxis2Placement3D", Location=point((0, 0, 0)))
        return f.create_entity("IfcLocalPlacement", PlacementRelTo=rel_to, RelativePlacement=axis2)

    # units (mm) + representation context
    mm = f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    units = f.create_entity("IfcUnitAssignment", Units=[mm])
    world = f.create_entity("IfcAxis2Placement3D", Location=point((0, 0, 0)),
                            Axis=f.create_entity("IfcDirection", DirectionRatios=(0., 0., 1.)),
                            RefDirection=f.create_entity("IfcDirection", DirectionRatios=(1., 0., 0.)))
    ctx = f.create_entity("IfcGeometricRepresentationContext", ContextType="Model",
                          CoordinateSpaceDimension=3, Precision=1e-5, WorldCoordinateSystem=world)
    body_ctx = f.create_entity("IfcGeometricRepresentationSubContext", ContextIdentifier="Body",
                               ContextType="Model", ParentContext=ctx, TargetView="MODEL_VIEW")

    project = f.create_entity("IfcProject", GlobalId=gid(), Name=ir.name or ir.id,
                              UnitsInContext=units, RepresentationContexts=[ctx])

    # spatial hierarchy: Project → Site → Building → Storey
    site_pl, bldg_pl = placement(), None
    site = f.create_entity("IfcSite", GlobalId=gid(), Name="Site", ObjectPlacement=site_pl,
                           CompositionType="ELEMENT")
    bldg_pl = placement(site_pl)
    building = f.create_entity("IfcBuilding", GlobalId=gid(), Name="Building",
                               ObjectPlacement=bldg_pl, CompositionType="ELEMENT")
    storey_pl = placement(bldg_pl)
    storey = f.create_entity("IfcBuildingStorey", GlobalId=gid(), Name="Storey",
                             ObjectPlacement=storey_pl, CompositionType="ELEMENT")
    f.create_entity("IfcRelAggregates", GlobalId=gid(), RelatingObject=project, RelatedObjects=[site])
    f.create_entity("IfcRelAggregates", GlobalId=gid(), RelatingObject=site, RelatedObjects=[building])
    f.create_entity("IfcRelAggregates", GlobalId=gid(), RelatingObject=building, RelatedObjects=[storey])

    # body: a rectangle (length × width) extruded by height
    profile = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA",
                              Position=f.create_entity("IfcAxis2Placement2D", Location=point((0, 0))),
                              XDim=length, YDim=width)
    solid = f.create_entity("IfcExtrudedAreaSolid", SweptArea=profile,
                            Position=f.create_entity("IfcAxis2Placement3D", Location=point((0, 0, 0))),
                            ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0., 0., 1.)),
                            Depth=height)
    shape = f.create_entity("IfcShapeRepresentation", ContextOfItems=body_ctx,
                            RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solid])
    product_shape = f.create_entity("IfcProductDefinitionShape", Representations=[shape])

    element = f.create_entity(ifc_class, GlobalId=gid(), Name=ir.name or ir.id,
                              ObjectPlacement=placement(storey_pl), Representation=product_shape)
    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=gid(),
                    RelatingStructure=storey, RelatedElements=[element])

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ir.id}.ifc"
    f.write(str(path))
    return path


def reimport_summary(path) -> dict:
    """Re-open the IFC and report what's in it — proves it's a valid, parseable model."""
    import ifcopenshell

    m = ifcopenshell.open(str(path))
    elements = m.by_type("IfcElement")
    units = [u.Name for u in (m.by_type("IfcSIUnit") or [])]
    return {"schema": m.schema, "element_classes": [e.is_a() for e in elements], "units": units}
