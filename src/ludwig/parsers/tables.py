"""Ruled tables from drawn lines and placed text, for DXF and PDF schedules (PLAN 3.2, 3.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Segment:
    """A straight drawn line, in drawing coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class Text:
    """One piece of text: its centre, its content and where it came from."""

    x: float
    y: float
    text: str
    origin: Any = None


def _levels(values: list[float], tolerance: float) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tolerance:
            out.append(v)
    return out


def grid(
    segments: list[Segment], texts: list[Text], y_up: bool = True, tolerance: float = 0.5
) -> list[list[list[Text]]]:
    """Cells of the ruled table formed by horizontal and vertical segments, top row first.

    Each cell holds its texts in reading order. Texts outside the rules are dropped. A
    merged cell repeats nowhere: its text lands in the cell that contains its centre.
    """
    dx = [abs(s.x0 - s.x1) for s in segments]
    dy = [abs(s.y0 - s.y1) for s in segments]
    flat = [s for s, a, b in zip(segments, dx, dy, strict=True) if b <= tolerance < a]
    upright = [s for s, a, b in zip(segments, dx, dy, strict=True) if a <= tolerance < b]
    ys = _levels([(s.y0 + s.y1) / 2 for s in flat], tolerance)
    xs = _levels([(s.x0 + s.x1) / 2 for s in upright], tolerance)
    if len(ys) < 2 or len(xs) < 2:
        return []
    if y_up:
        ys.reverse()  # top row first
    rows: list[list[list[Text]]] = [[[] for _ in xs[:-1]] for _ in ys[:-1]]
    for t in texts:
        r = next((i for i in range(len(ys) - 1) if _between(t.y, ys[i], ys[i + 1])), None)
        c = next((j for j in range(len(xs) - 1) if _between(t.x, xs[j], xs[j + 1])), None)
        if r is not None and c is not None:
            rows[r][c].append(t)
    for row in rows:
        for cell in row:
            cell.sort(key=lambda t: ((-t.y if y_up else t.y), t.x))
    return rows


def _between(v: float, a: float, b: float) -> bool:
    return min(a, b) < v < max(a, b)


def cell_text(cell: list[Text]) -> str | None:
    """The cell's texts joined by spaces, or None when empty."""
    text = " ".join(t.text.strip() for t in cell if t.text.strip())
    return text or None
