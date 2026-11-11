"""IFC parser: windows and doors into elements, one element per mark (SPEC section 4)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from ludwig.model import Element, ElementType, ParseWarning, Side, SourceKind, SourceRef

_MAPPING_KEYS = {"classes", "mark", "width", "height", "props", "name_as_value_is_empty"}
_PROP_KEYS = {"paths", "as", "ignore"}
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def load_mapping(path: str | Path | None = None) -> dict[str, Any]:
    """Load and check an IFC mapping file; the built-in default when no path is given."""
    if path is None:
        text = resources.files("ludwig.parsers.mappings").joinpath("ifc_default.yaml").read_text()
    else:
        text = Path(path).read_text()
    mapping = yaml.safe_load(text) or {}
    unknown = set(mapping) - _MAPPING_KEYS
    if unknown:
        raise ValueError(f"IFC mapping: unknown keys {sorted(unknown)}")
    for etype in mapping.get("classes", {}).values():
        ElementType(etype)  # raises on an unknown element type
    for name, spec in mapping.get("props", {}).items():
        bad = set(spec) - _PROP_KEYS
        if bad or spec.get("as") not in ("number", "text"):
            raise ValueError(f"IFC mapping: prop {name} is malformed")
    return mapping


@dataclass
class _Reader:
    """Reads mapped values from one occurrence and counts placeholder values."""

    mapping: dict[str, Any]
    placeholders: Counter

    def value(self, occ: Any, psets: dict, paths: list[str]) -> tuple[Any, str | None]:
        for path in paths:
            raw = self._raw(occ, psets, path)
            if raw is None:
                continue
            if isinstance(raw, str):
                raw = raw.strip()
                if not raw:
                    continue
                if self.mapping.get("name_as_value_is_empty") and raw == _prop_name(path):
                    self.placeholders[path] += 1
                    continue
            return raw, path
        return None, None

    @staticmethod
    def _raw(occ: Any, psets: dict, path: str) -> Any:
        kind, _, name = path.partition(":")
        if kind == "attr":
            return getattr(occ, name, None)
        if kind == "type_attr":
            import ifcopenshell.util.element as ue

            typ = ue.get_type(occ)
            return getattr(typ, name, None) if typ is not None else None
        if kind == "pset":
            pset, _, prop = name.partition(".")
            return psets.get(pset, {}).get(prop)
        raise ValueError(f"IFC mapping: bad value path {path!r}")


def _prop_name(path: str) -> str:
    return path.partition(":")[2].partition(".")[2] or path.partition(":")[2]


def _as_number(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        return float(raw)
    match = _NUMBER.search(str(raw))
    return float(match.group().replace(",", ".")) if match else None


def parse(
    path: str | Path, mapping: dict[str, Any] | None = None
) -> tuple[list[Element], list[ParseWarning]]:
    """Read windows and doors from an IFC file. Never raises on bad input."""
    file = str(path)
    mapping = mapping if mapping is not None else load_mapping()
    try:
        import ifcopenshell
        import ifcopenshell.util.element as ue
        import ifcopenshell.util.unit as uu

        model = ifcopenshell.open(file)
        to_mm = uu.calculate_unit_scale(model) * 1000.0
    except Exception as exc:  # noqa: BLE001 - any read failure becomes a warning
        return [], [ParseWarning(file, f"cannot read IFC file: {exc}")]

    warnings: list[ParseWarning] = []
    reader = _Reader(mapping, Counter())
    groups: dict[tuple, list[tuple[str, str | None]]] = defaultdict(list)

    for cls, etype in sorted(mapping.get("classes", {}).items()):
        try:
            occurrences = model.by_type(cls)
        except RuntimeError:
            continue  # class not in this schema
        for occ in occurrences:
            guid = occ.GlobalId
            src = SourceRef(file, SourceKind.IFC, ifc_guid=guid)
            try:
                psets = ue.get_psets(occ)
                mark, _ = reader.value(occ, psets, mapping.get("mark", []))
                dims = []
                for key in ("width", "height"):
                    raw, used = reader.value(occ, psets, mapping.get(key, []))
                    number = _as_number(raw) if raw is not None else None
                    if raw is not None and number is None:
                        warnings.append(ParseWarning(file, f"{used}: not a length: {raw!r}", src))
                    dims.append(round(number * to_mm, 1) if number is not None else None)
                props = {}
                for name, spec in sorted(mapping.get("props", {}).items()):
                    raw, used = reader.value(occ, psets, spec["paths"])
                    if raw is None or str(raw) in spec.get("ignore", []):
                        continue
                    if spec["as"] == "number":
                        number = _as_number(raw)
                        if number is None:
                            warnings.append(
                                ParseWarning(file, f"{used}: not a number: {raw!r}", src)
                            )
                            continue
                        props[name] = number
                    else:
                        props[name] = str(raw)
                container = ue.get_container(occ)
                location = getattr(container, "Name", None) or None
            except Exception as exc:  # noqa: BLE001
                warnings.append(ParseWarning(file, f"{cls} {guid}: cannot read: {exc}", src))
                continue
            mark_key = str(mark) if mark is not None else f"\0{guid}"
            key = (etype, mark_key, dims[0], dims[1], tuple(sorted(props.items())))
            groups[key].append((guid, location))

    for path_, count in sorted(reader.placeholders.items()):
        warnings.append(
            ParseWarning(file, f"{path_}: {count} values equal the property name; read as not set")
        )

    elements = []
    for (etype, mark_key, width, height, props), members in groups.items():
        guids = sorted(g for g, _ in members)
        locations = {loc for _, loc in members}
        elements.append(
            Element(
                id=f"{Path(file).name}#{guids[0]}",
                side=Side.ARCHITECT,
                type=ElementType(etype),
                sources=[SourceRef(file, SourceKind.IFC, ifc_guid=g) for g in guids],
                mark=None if mark_key.startswith("\0") else mark_key,
                quantity=len(guids),
                width_mm=width,
                height_mm=height,
                location=locations.pop() if len(locations) == 1 else None,
                props=dict(props),
            )
        )
    elements.sort(key=lambda e: (e.type.value, e.mark or "", e.id))
    return elements, warnings
