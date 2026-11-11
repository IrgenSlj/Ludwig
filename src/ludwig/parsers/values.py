"""Reading numbers and lengths from cell and property values."""

from __future__ import annotations

import re
from typing import Any

_NUMBER = re.compile(r"-?\d[\d.,]*")
UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0}


def as_number(raw: Any) -> float | None:
    """First number in a value; '1.200,5' and '1200,5' read as 1200.5. None if there is none."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int | float):
        return float(raw)
    match = _NUMBER.search(str(raw))
    if not match:
        return None
    text = match.group().rstrip(".,")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def as_int(raw: Any) -> int | None:
    """A whole, non-negative number, or None."""
    number = as_number(raw)
    if number is None or number < 0 or not number.is_integer():
        return None
    return int(number)
