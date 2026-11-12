"""DXF parser: block references with attributes become elements (SPEC section 4, PLAN 3.1)."""

from __future__ import annotations

import fnmatch
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from ludwig.model import (
    STANDARD_PROPS,
    Element,
    ElementType,
    ParseWarning,
    Side,
    SourceKind,
    SourceRef,
    normalise_mark,
)
from ludwig.parsers.values import UNIT_TO_MM, as_number, as_term

DEFAULT_MAPPING = Path(__file__).parent / "mappings" / "dxf_default.yaml"
_MAPPING_KEYS = {"layers", "blocks", "attributes", "units", "extents", "props"}
_FIELDS = {"mark", "width_mm", "height_mm", "location"}
# $INSUNITS codes -> millimetres; 0 (unitless) is read as millimetres with a warning.
_INSUNITS_TO_MM = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}


def load_mapping(path: str | Path | None = None) -> dict[str, Any]:
    """Load and check a DXF mapping (the default when no path is given)."""
    path = Path(path) if path else DEFAULT_MAPPING
    mapping = yaml.safe_load(path.read_text()) or {}
    unknown = set(mapping) - _MAPPING_KEYS
    if unknown:
        raise ValueError(f"{path}: unknown keys {sorted(unknown)}")
    for etype in mapping.get("blocks", {}).values():
        ElementType(etype)
    if set(mapping.get("attributes", {})) - _FIELDS:
        raise ValueError(f"{path}: attributes takes {sorted(_FIELDS)}")
    if mapping.get("units", "mm") not in UNIT_TO_MM:
        raise ValueError(f"{path}: units must be one of {sorted(UNIT_TO_MM)}")
    for name, axis in mapping.get("extents", {}).items():
        if name not in ("width_mm", "height_mm") or axis not in ("x", "y"):
            raise ValueError(f"{path}: extents maps width_mm/height_mm to x or y")
    for name, spec in mapping.get("props", {}).items():
        if name not in STANDARD_PROPS or set(spec) - {"tags", "as", "values"}:
            raise ValueError(f"{path}: prop {name} is malformed")
        if spec.get("as") not in ("number", "text") or not spec.get("tags"):
            raise ValueError(f"{path}: prop {name} needs tags and as: number|text")
    return mapping


def _first(attribs: dict[str, str], tags: list[str]) -> tuple[str | None, str | None]:
    for tag in tags:
        value = attribs.get(tag.upper(), "").strip()
        if value:
            return value, tag.upper()
    return None, None


def _extent(insert: Any, axis: str) -> float | None:
    """Size of the block reference along its own axis, scale included, rotation excluded."""
    from ezdxf import bbox

    block = insert.block()
    if block is None:
        return None
    box = bbox.extents(e for e in block if e.dxftype() != "ATTDEF")
    if not box.has_data:
        return None
    size = box.size.x if axis == "x" else box.size.y
    scale = abs(insert.dxf.xscale if axis == "x" else insert.dxf.yscale)
    return size * scale


def parse(
    path: str | Path, mapping: dict[str, Any] | None = None
) -> tuple[list[Element], list[ParseWarning]]:
    """Read joinery block references from a DXF file. Never raises on bad input."""
    file = str(path)
    mapping = mapping if mapping is not None else load_mapping()
    try:
        from ezdxf import recover

        doc, auditor = recover.readfile(file)
    except Exception as exc:  # noqa: BLE001 - any read failure becomes a warning
        return [], [ParseWarning(file, f"cannot read DXF file: {exc}")]

    warnings: list[ParseWarning] = []
    if auditor.has_errors:
        warnings.append(ParseWarning(file, f"{len(auditor.errors)} damaged entities repaired"))
    insunits = doc.header.get("$INSUNITS", 0)
    drawing_mm = _INSUNITS_TO_MM.get(insunits)
    if drawing_mm is None:
        drawing_mm = 1.0
        warnings.append(ParseWarning(file, f"$INSUNITS {insunits}: extents read as millimetres"))
    attr_mm = UNIT_TO_MM[mapping.get("units", "mm")]
    layers = {name.casefold() for name in mapping.get("layers", [])}
    blocks = {pattern.casefold(): etype for pattern, etype in mapping.get("blocks", {}).items()}
    fields = mapping.get("attributes", {})
    groups: dict[tuple, list[tuple[SourceRef, str | None]]] = defaultdict(list)

    for insert in doc.modelspace().query("INSERT"):
        name = insert.dxf.name.casefold()
        etype = next((t for p, t in blocks.items() if fnmatch.fnmatchcase(name, p)), None)
        if etype is None or (layers and insert.dxf.layer.casefold() not in layers):
            continue
        src = SourceRef(file, SourceKind.DXF, dxf_handle=insert.dxf.handle, layer=insert.dxf.layer)
        try:
            attribs = {a.dxf.tag.upper(): a.dxf.text for a in insert.attribs}
            mark, _ = _first(attribs, fields.get("mark", []))
            location, _ = _first(attribs, fields.get("location", []))
            dims = []
            for field in ("width_mm", "height_mm"):
                raw, tag = _first(attribs, fields.get(field, []))
                if raw is not None:
                    number = as_number(raw)
                    if number is None:
                        warnings.append(ParseWarning(file, f"{tag}: not a number {raw!r}", src))
                    dims.append(round(number * attr_mm, 1) if number is not None else None)
                    continue
                axis = mapping.get("extents", {}).get(field)
                size = _extent(insert, axis) if axis else None
                dims.append(round(size * drawing_mm, 1) if size is not None else None)
            props: dict[str, Any] = {}
            for prop, spec in sorted(mapping.get("props", {}).items()):
                raw, tag = _first(attribs, spec["tags"])
                if raw is None:
                    continue
                if spec["as"] == "number":
                    number = as_number(raw)
                    if number is None:
                        warnings.append(ParseWarning(file, f"{tag}: not a number {raw!r}", src))
                        continue
                    props[prop] = number
                else:
                    props[prop] = as_term(raw, spec.get("values"))
        except Exception as exc:  # noqa: BLE001
            msg = f"INSERT {insert.dxf.handle}: cannot read: {exc}"
            warnings.append(ParseWarning(file, msg, src))
            continue
        mark = normalise_mark(mark)
        mark_key = mark if mark is not None else f"\0{insert.dxf.handle}"
        key = (etype, mark_key, dims[0], dims[1], tuple(sorted(props.items())))
        groups[key].append((src, location))

    elements = []
    for (etype, mark_key, width, height, props), members in groups.items():
        sources = sorted((s for s, _ in members), key=lambda s: s.dxf_handle or "")
        locations = {loc for _, loc in members}
        elements.append(
            Element(
                id=f"{Path(file).name}#{sources[0].dxf_handle}",
                side=Side.ARCHITECT,
                type=ElementType(etype),
                sources=sources,
                mark=None if mark_key.startswith("\0") else mark_key,
                quantity=len(sources),
                width_mm=width,
                height_mm=height,
                location=locations.pop() if len(locations) == 1 else None,
                props=dict(props),
            )
        )
    elements.sort(key=lambda e: (e.type.value, e.mark or "", e.id))
    return elements, warnings
