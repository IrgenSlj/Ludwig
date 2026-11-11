"""Schedule parser: an Excel or CSV table read through a column mapping (SPEC section 4)."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import yaml

from ludwig.model import (
    Element,
    ElementType,
    ParseWarning,
    Side,
    SourceKind,
    SourceRef,
    normalise_mark,
)
from ludwig.parsers.values import UNIT_TO_MM, as_int, as_number

_MAPPING_KEYS = {"sheet", "header_row", "type", "columns", "units", "props", "empty_values"}
_FIELDS = {"mark", "quantity", "width_mm", "height_mm", "depth_mm", "location"}
_LENGTHS = {"width_mm", "height_mm", "depth_mm"}


def load_mapping(path: str | Path) -> dict[str, Any]:
    """Load and check a schedule mapping file."""
    return load_mapping_dict(yaml.safe_load(Path(path).read_text()) or {}, str(path))


def load_mapping_dict(mapping: dict[str, Any], path: str = "mapping") -> dict[str, Any]:
    """Check a schedule mapping given as a dict; raises ValueError naming the problem."""
    unknown = set(mapping) - _MAPPING_KEYS
    if unknown:
        raise ValueError(f"{path}: unknown keys {sorted(unknown)}")
    bad_fields = set(mapping.get("columns", {})) - _FIELDS
    if bad_fields:
        raise ValueError(f"{path}: unknown columns entries {sorted(bad_fields)}")
    if mapping.get("units", "mm") not in UNIT_TO_MM:
        raise ValueError(f"{path}: units must be one of {sorted(UNIT_TO_MM)}")
    typ = mapping.get("type")
    if isinstance(typ, str):
        ElementType(typ)
    elif isinstance(typ, dict):
        if not {"column", "values"} <= set(typ) <= {"column", "values", "other"}:
            raise ValueError(f"{path}: type needs column and values (other: skip|warn)")
        if typ.get("other", "warn") not in ("skip", "warn"):
            raise ValueError(f"{path}: type.other must be skip or warn")
        for value in typ["values"].values():
            ElementType(value)
    else:
        raise ValueError(f"{path}: type is required")
    for name, spec in mapping.get("props", {}).items():
        if set(spec) - {"column", "as"} or spec.get("as") not in ("number", "text"):
            raise ValueError(f"{path}: prop {name} is malformed")
    return mapping


def _text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip().lower()


def _cell(col: int, row: int) -> str:
    letters = ""
    col += 1
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def _read_rows(path: Path, sheet: str | None) -> tuple[list[list[Any]], str | None]:
    """All rows as lists, and the sheet name used (None for CSV)."""
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows, ws.title
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [list(r) for r in csv.reader(io.StringIO(text), dialect)], None


def parse(
    path: str | Path, mapping: dict[str, Any], side: Side = Side.ARCHITECT
) -> tuple[list[Element], list[ParseWarning]]:
    """Read one schedule into elements. Never raises on bad input."""
    path = Path(path)
    file = str(path)
    try:
        rows, sheet = _read_rows(path, mapping.get("sheet"))
    except Exception as exc:  # noqa: BLE001 - any read failure becomes a warning
        return [], [ParseWarning(file, f"cannot read schedule: {exc}")]

    kind = SourceKind.ERP if side is Side.ERP else SourceKind.SHEET
    header_row = int(mapping.get("header_row", 1))
    if len(rows) < header_row:
        return [], [ParseWarning(file, f"no header row {header_row}")]
    header = {
        str(h).strip().lower(): i for i, h in enumerate(rows[header_row - 1]) if h is not None
    }
    empty = {_text(v) for v in mapping.get("empty_values", ["", "-"])}
    warnings: list[ParseWarning] = []

    def find(column: str, purpose: str) -> int | None:
        idx = header.get(column.strip().lower())
        if idx is None:
            warnings.append(
                ParseWarning(file, f"column '{column}' ({purpose}) not found in row {header_row}")
            )
        return idx

    typ = mapping["type"]
    columns = {f: find(c, f) for f, c in mapping.get("columns", {}).items()}
    type_col = find(typ["column"], "type") if isinstance(typ, dict) else None
    prop_cols = {n: find(s["column"], n) for n, s in mapping.get("props", {}).items()}
    to_mm = UNIT_TO_MM[mapping.get("units", "mm")]

    elements = []
    for row_no, row in enumerate(rows[header_row:], start=header_row + 1):

        def get(idx: int | None, _row: list = row) -> Any:
            if idx is None or idx >= len(_row):
                return None
            value = _row[idx]
            if isinstance(value, str):
                value = value.strip()
            return None if value is None or _text(value) in empty else value

        def ref(idx: int | None, _row_no: int = row_no) -> SourceRef:
            cell = _cell(idx, _row_no) if idx is not None else f"A{_row_no}"
            return SourceRef(file, kind, sheet=sheet, cell=cell)

        used = [i for i in [*columns.values(), type_col, *prop_cols.values()] if i is not None]
        if all(get(i) is None for i in used):
            continue

        if isinstance(typ, dict):
            raw_type = get(type_col)
            lookup = {str(k).strip().lower(): v for k, v in typ["values"].items()}
            etype = lookup.get(str(raw_type).strip().lower()) if raw_type is not None else None
            if etype is None:
                if typ.get("other", "warn") == "warn":
                    msg = f"unknown type {raw_type!r}"
                    warnings.append(ParseWarning(file, msg, ref(type_col)))
                continue
        else:
            etype = typ

        values: dict[str, Any] = {}
        field_sources: dict[str, SourceRef] = {}
        for name, idx in columns.items():
            raw = get(idx)
            if raw is None:
                values[name] = None
                continue
            field_sources[name] = ref(idx)
            if name in _LENGTHS:
                number = as_number(raw)
                values[name] = round(number * to_mm, 1) if number is not None else None
            elif name == "quantity":
                values[name] = as_int(raw)
            else:
                values[name] = str(raw)
            if values[name] is None:
                warnings.append(ParseWarning(file, f"{name}: cannot read {raw!r}", ref(idx)))

        props: dict[str, Any] = {}
        for name, idx in prop_cols.items():
            raw = get(idx)
            if raw is None:
                continue
            if mapping["props"][name]["as"] == "number":
                number = as_number(raw)
                if number is None:
                    warnings.append(ParseWarning(file, f"{name}: not a number {raw!r}", ref(idx)))
                    continue
                props[name] = number
            else:
                props[name] = str(raw)
            field_sources[f"props.{name}"] = ref(idx)

        anchor = columns.get("mark") if columns.get("mark") is not None else (used or [None])[0]
        quantity = values["quantity"] if "quantity" in columns else 1
        elements.append(
            Element(
                id=f"{path.name}!{sheet or ''}!{row_no}",
                side=side,
                type=ElementType(etype),
                sources=[ref(anchor)],
                mark=normalise_mark(values.get("mark")),
                quantity=quantity,
                width_mm=values.get("width_mm"),
                height_mm=values.get("height_mm"),
                depth_mm=values.get("depth_mm"),
                location=values.get("location"),
                props=props,
                field_sources=field_sources,
            )
        )
    return elements, warnings
