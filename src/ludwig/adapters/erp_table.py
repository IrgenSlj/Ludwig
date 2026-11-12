"""Production export importer: a CSV/Excel table read through a mapping (SPEC section 4).

The mapping format is the schedule mapping (column names, units, type vocabulary); no
vendor is named in code. Elements come out on the `erp` side with `erp` sources.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ludwig.model import Element, ParseWarning, Side
from ludwig.parsers import schedule


def load_mapping(path: str | Path) -> dict[str, Any]:
    """Load and check an export mapping; raises ValueError naming the problem."""
    return schedule.load_mapping(path)


def parse(path: str | Path, mapping: dict[str, Any]) -> tuple[list[Element], list[ParseWarning]]:
    """Read one production export into erp-side elements. Never raises on bad input."""
    return schedule.parse(path, mapping, side=Side.ERP)
