"""Vector PDF schedules: text with positions and ruled tables (SPEC section 4, PLAN 3.3).

Only text the PDF actually contains is read. A page without vector text (a scan) gives a
parse warning; nothing is guessed from images.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ludwig.model import Element, ParseWarning, Side, SourceKind, SourceRef
from ludwig.parsers import schedule
from ludwig.parsers.tables import Segment, Text, cell_text, grid


def load_mapping(path: str | Path) -> dict[str, Any]:
    """A schedule mapping plus optional `pages` (1-based) to read; raises ValueError."""
    mapping = yaml.safe_load(Path(path).read_text()) or {}
    pages = mapping.get("pages")
    if pages is not None and not (
        isinstance(pages, list) and all(isinstance(p, int) and p >= 1 for p in pages)
    ):
        raise ValueError(f"{path}: pages must be a list of page numbers from 1")
    rest = {k: v for k, v in mapping.items() if k != "pages"}
    schedule.load_mapping_dict(rest, str(path))
    return mapping


def _box(cell: list[Text]) -> tuple[float, float, float, float] | None:
    words = [t.origin[1] for t in cell]
    if not words:
        return None
    x0, top = min(w["x0"] for w in words), min(w["top"] for w in words)
    x1, bottom = max(w["x1"] for w in words), max(w["bottom"] for w in words)
    return (round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1))


def _page_table(page: Any, number: int) -> tuple[list[list[list[Text]]], str | None]:
    """The ruled table on one page, or the reason there is none."""
    words = page.extract_words()
    if not words:
        return [], "no vector text, not read"
    segments = [Segment(e["x0"], e["top"], e["x1"], e["bottom"]) for e in page.edges]
    texts = [Text((w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2, w["text"], (number, w))
             for w in words]  # fmt: skip
    rows = grid(segments, texts, y_up=False)
    return rows, None if rows else "no ruled table"


def parse(path: str | Path, mapping: dict[str, Any]) -> tuple[list[Element], list[ParseWarning]]:
    """Read the ruled schedule table on the mapped pages. Never raises on bad input."""
    file = str(path)
    warnings: list[ParseWarning] = []
    cells: list[list[list[Text]]] = []
    header: list[str | None] | None = None
    header_row = int(mapping.get("header_row", 1))
    try:
        import pdfplumber

        with pdfplumber.open(file) as pdf:
            numbers = mapping.get("pages") or range(1, len(pdf.pages) + 1)
            for number in numbers:
                if number > len(pdf.pages):
                    warnings.append(ParseWarning(file, f"page {number}: not in the file"))
                    continue
                rows, problem = _page_table(pdf.pages[number - 1], number)
                if problem:
                    where = SourceRef(file, SourceKind.PDF, page=number)
                    warnings.append(ParseWarning(file, f"page {number}: {problem}", where))
                    continue
                if header is None:
                    if len(rows) >= header_row:
                        header = [cell_text(c) for c in rows[header_row - 1]]
                    cells.extend(rows)
                else:  # a continuation page repeats the header; keep only the body
                    cells.extend(r for r in rows if [cell_text(c) for c in r] != header)
    except Exception as exc:  # noqa: BLE001 - any read failure becomes a warning
        return [], [*warnings, ParseWarning(file, f"cannot read PDF file: {exc}")]
    if not cells:
        return [], warnings

    def locate(col: int | None, row: int) -> SourceRef:
        cell = cells[row - 1][col] if col is not None else [t for c in cells[row - 1] for t in c]
        page = cell[0].origin[0] if cell else None
        return SourceRef(file, SourceKind.PDF, page=page, bbox=_box(cell),
                         cell=schedule.cell_name(col or 0, row))  # fmt: skip

    rows = [[cell_text(c) for c in row] for row in cells]
    table = {k: v for k, v in mapping.items() if k != "pages"}
    found, warned = schedule.parse_rows(rows, file, Path(file).name, table, Side.ARCHITECT, locate)
    return found, warnings + warned
