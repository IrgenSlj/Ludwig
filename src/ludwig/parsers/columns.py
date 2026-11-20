"""Mapping builder: read a table's head and propose a column mapping (PLAN 5.7).

Deterministic: headers and cell values are matched against `mappings/column_names.yaml`.
The proposal is a starting point a person confirms; it never runs a check by itself.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from ludwig.model import Side
from ludwig.parsers import schedule
from ludwig.parsers.values import as_number

HEAD_ROWS = 10  # rows searched for the header
SAMPLE_ROWS = 5
MAX_VALUES = 30  # distinct values listed per column
_UNIT = re.compile(r"[\(\[]\s*(mm|cm|m)\s*[\)\]]", re.IGNORECASE)


def normalise(text: Any) -> str:
    """Header or value as compared: lower case, no bracketed unit, letters and digits only."""
    text = re.sub(r"[\(\[].*?[\)\]]", "", str(text).lower())
    return "".join(ch for ch in text if ch.isalnum())


@cache
def _names() -> dict[str, Any]:
    raw = yaml.safe_load((Path(__file__).parent / "mappings" / "column_names.yaml").read_text())

    def lookup(names: list[str]) -> set[str]:
        return {normalise(n) for n in names}

    return {
        "columns": {f: lookup(n) for f, n in raw["columns"].items()},
        "props": {p: (s["as"], lookup(s["names"])) for p, s in raw["props"].items()},
        "type_column": lookup(raw["type_column"]),
        "types": {t: lookup(n) for t, n in raw["types"].items()},
        "opening_direction": {d: lookup(n) for d, n in raw["opening_direction"].items()},
    }


def _known_headers() -> set[str]:
    names = _names()
    known = set().union(*names["columns"].values(), names["type_column"])
    return known.union(*(n for _, n in names["props"].values()))


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def find_header_row(rows: list[list[Any]]) -> int:
    """1-based row among the first few with the most recognised headers (1 if none)."""
    known = _known_headers()
    best, best_hits = 1, 0
    for i, row in enumerate(rows[:HEAD_ROWS], start=1):
        hits = sum(normalise(c) in known for c in row if c is not None)
        if hits > best_hits:
            best, best_hits = i, hits
    return best


def _pick(headers: list[str], wanted: set[str], taken: set[str]) -> str | None:
    for h in headers:
        if h and h not in taken and normalise(h) in wanted:
            return h
    return None


def _translate(values: list[str], vocabulary: dict[str, set[str]]) -> dict[str, str]:
    out = {}
    for v in values:
        for target, names in vocabulary.items():
            if normalise(v) in names:
                out[v] = target
                break
    return out


def _units(headers: list[str], chosen: dict[str, str], values: dict[str, list[str]]) -> str:
    for field in ("width_mm", "height_mm"):
        header = chosen.get(field)
        if header and (m := _UNIT.search(header)):
            return m.group(1).lower()
    numbers = [
        n for f in ("width_mm", "height_mm") if chosen.get(f)
        for n in (as_number(v) for v in values.get(chosen[f], [])) if n is not None
    ]  # fmt: skip
    # Window and door sizes in metres are all below 10; in mm or cm they are not.
    if numbers and max(numbers) < 10:
        return "m"
    return "mm"


def propose(rows: list[list[Any]], side: Side, header_row: int | None = None) -> dict[str, Any]:
    """Headers, sample rows, distinct values per column and a proposed mapping."""
    header_row = header_row or find_header_row(rows)
    head = rows[header_row - 1] if len(rows) >= header_row else []
    headers = [_cell(h) for h in head]
    body = [[_cell(c) for c in r] for r in rows[header_row:]]
    body = [r for r in body if any(r)]
    values: dict[str, list[str]] = {}
    for i, h in enumerate(headers):
        if not h:
            continue
        seen: list[str] = []
        for r in body:
            v = r[i] if i < len(r) else ""
            if v and v != "-" and v not in seen:
                seen.append(v)
                if len(seen) == MAX_VALUES:
                    break
        values[h] = seen

    names = _names()
    taken: set[str] = set()
    columns: dict[str, str] = {}
    for field, wanted in names["columns"].items():
        if h := _pick(headers, wanted, taken):
            columns[field] = h
            taken.add(h)

    mapping: dict[str, Any] = {"header_row": header_row, "type": "frame"}
    if side is Side.ERP and (h := _pick(headers, names["type_column"], taken)):
        found = _translate(values.get(h, []), names["types"])
        if found:
            mapping["type"] = {"column": h, "values": found, "other": "skip"}
            taken.add(h)
    mapping["units"] = _units(headers, columns, values)
    mapping["columns"] = columns

    props: dict[str, Any] = {}
    for prop, (kind, wanted) in names["props"].items():
        if h := _pick(headers, wanted, taken):
            spec: dict[str, Any] = {"column": h, "as": kind}
            if prop == "fire_rating_min":
                # A system with a fire rating column leaves it empty for "none"; the web app
                # shows this as a choice the person confirms.
                spec["default"] = 0
            if prop == "opening_direction":
                found = _translate(values.get(h, []), names["opening_direction"])
                if found:
                    spec["values"] = found
            props[prop] = spec
            taken.add(h)
    if props:
        mapping["props"] = props
    return {
        "header_row": header_row,
        "headers": headers,
        "sample": body[:SAMPLE_ROWS],
        "values": values,
        "mapping": mapping,
    }


def read_rows(path: Path, sheet: str | None = None) -> list[list[Any]]:
    """All rows of a spreadsheet or CSV file (raises on an unreadable file)."""
    return schedule.read_rows(path, sheet)[0]


def sheets(path: Path) -> list[str]:
    """Sheet names of a workbook; empty for CSV."""
    if path.suffix.lower() not in (".xlsx", ".xlsm"):
        return []
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def columns_used(mapping: dict[str, Any]) -> set[str]:
    """Every header a mapping names, lower-cased as the parser compares them."""
    used = set(mapping.get("columns", {}).values())
    if isinstance(mapping.get("type"), dict):
        used.add(mapping["type"]["column"])
    used |= {spec["column"] for spec in mapping.get("props", {}).values()}
    return {str(c).strip().lower() for c in used}


def fits(mapping: dict[str, Any], headers: list[str]) -> bool:
    """True when every column the mapping names is among the headers."""
    used = columns_used(mapping)
    return bool(used) and used <= {h.strip().lower() for h in headers if h}


def to_yaml(mapping: dict[str, Any], filename: str) -> str:
    """The mapping as a file, checked first; raises ValueError naming the problem."""
    schedule.load_mapping_dict(mapping, filename)
    header = f"# Column mapping for {filename}, made in the Ludwig web app.\n"
    return header + yaml.safe_dump(mapping, sort_keys=False, allow_unicode=True)
