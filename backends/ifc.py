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
    geom = GeometryService()
    ifc_map = load().get("ifc_map", {})
    ifc_class = ifc_map.get(ir.type, "IfcBuildingElementProxy")

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

    def massing(el):
        """A representative bbox solid for one element, centred on its actual bbox centre (so it
        co-registers with the centred STEP/CadQuery solid — not offset to z=0)."""
        length, width, height = geom.bbox(el.geometry)
        cx, cy, cz = geom.bbox_center(el.geometry)
        profile = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA",
                                  Position=f.create_entity("IfcAxis2Placement2D", Location=point((0, 0))),
                                  XDim=length, YDim=width)
        solid = f.create_entity("IfcExtrudedAreaSolid", SweptArea=profile,
                                Position=f.create_entity("IfcAxis2Placement3D", Location=point((cx, cy, cz - height / 2))),
                                ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0., 0., 1.)),
                                Depth=height)
        shape = f.create_entity("IfcShapeRepresentation", ContextOfItems=body_ctx,
                                RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solid])
        return f.create_entity("IfcProductDefinitionShape", Representations=[shape])

    def make_element(el, ifc_cls, *, body=True):
        return f.create_entity(ifc_cls, GlobalId=gid(), Name=el.name or el.id,
                               ObjectPlacement=placement(storey_pl),
                               Representation=massing(el) if body else None)

    # An Assembly decomposes into its children (IfcRelAggregates); each child is its own IfcElement
    # with geometry, so the BIM model mirrors the IR tree. A plain Part is a single element.
    children = getattr(ir, "children", None) or []
    if children:
        element = make_element(ir, ifc_class, body=False)  # the assembly itself carries no massing
        kids = [make_element(c, ifc_map.get(c.type, "IfcBuildingElementProxy")) for c in children]
        f.create_entity("IfcRelAggregates", GlobalId=gid(), RelatingObject=element, RelatedObjects=kids)
    else:
        element = make_element(ir, ifc_class)
    # --- material assignment + property sets ---
    _add_material(f, ir, element, ifc_class, load())
    _add_property_sets(f, ir, element)

    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=gid(),
                    RelatingStructure=storey, RelatedElements=[element])

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ir.id}.ifc"
    f.write(str(path))
    return path


# --- module-level helpers: material + property-set authoring (called from compile) ---


def _material_for(el, ifc_map, std):
    """Resolve the material key for an element from standards.yaml ifc_material_map."""
    mat_map = std.get("ifc_material_map", {})
    return mat_map.get(el.type)


def _add_material(f, el, ifc_element, ifc_cls, std):
    """Create an IfcMaterial + IfcRelAssociatesMaterial for the element, if a material is
    defined in standards.yaml. Uses `ifc_material_map` to resolve Element.type -> material id."""
    key = _material_for(el, None, std)
    if not key:
        return
    mat_def = std.get("materials", {}).get(key)
    if not mat_def:
        return
    mat_name = mat_def.get("ifc_material", key.title())
    material = f.create_entity("IfcMaterial", Name=mat_name)
    f.create_entity("IfcRelAssociatesMaterial", GlobalId=_gid(f),
                    RelatedObjects=[ifc_element],
                    RelatingMaterial=material)


def _add_property_sets(f, el, ifc_element):
    """Create IFC property sets for the element based on its material definition in standards.yaml.
    Currently adds Pset_PrecastConcrete for precast concrete elements; extensible to other property
    sets as new materials are defined."""
    from toolkit.standards import load as _load
    std = _load()
    key = _material_for(el, None, std)
    if not key:
        return
    mat_def = std.get("materials", {}).get(key)
    if not mat_def:
        return
    pset_name = mat_def.get("ifc_property_set")
    if not pset_name:
        return

    # Skip non-material-specific props
    skip_keys = {"ifc_material", "ifc_property_set"}
    props = []
    for k, v in mat_def.items():
        if k in skip_keys:
            continue
        # Map Python type to IFC type
        if isinstance(v, bool):
            ifc_type = "IfcBoolean"
        elif isinstance(v, (int, float)):
            ifc_type = "IfcReal"
            v = float(v)
        else:
            ifc_type = "IfcLabel"
        prop = f.create_entity("IfcPropertySingleValue", Name=k.replace("_", " ").title(),
                               NominalValue=f.create_entity(ifc_type, v))
        props.append(prop)

    if not props:
        return
    pset = f.create_entity("IfcPropertySet", GlobalId=_gid(f), Name=pset_name,
                           HasProperties=props)
    f.create_entity("IfcRelDefinesByProperties", GlobalId=_gid(f),
                    RelatedObjects=[ifc_element],
                    RelatingPropertyDefinition=pset)


def _gid(f):
    """Short-lived GUID factory — wraps ifcopenshell.guid.new()."""
    import ifcopenshell.guid as _guid
    return _guid.new()


# Module-level self-registration
from backends.registry import register as _register
import sys as _sys
_register(_sys.modules[__name__])


def reimport_summary(path) -> dict:
    """Re-open the IFC and report what's in it — proves it's a valid, parseable model."""
    import ifcopenshell

    m = ifcopenshell.open(str(path))
    elements = m.by_type("IfcElement")
    units = [u.Name for u in (m.by_type("IfcSIUnit") or [])]
    # children aggregated under an IfcElementAssembly (decomposition), if any
    decomposed = sum(len(r.RelatedObjects) for r in m.by_type("IfcRelAggregates")
                     if r.RelatingObject.is_a("IfcElementAssembly"))
    # material + property-set evidence
    materials = [m.Name for m in m.by_type("IfcMaterial")]
    property_sets = [p.Name for p in m.by_type("IfcPropertySet")]
    return {"schema": m.schema, "element_classes": [e.is_a() for e in elements],
            "units": units, "assembly_children": decomposed,
            "materials": materials, "property_sets": property_sets}
