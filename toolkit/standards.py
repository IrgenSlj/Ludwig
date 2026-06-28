"""Loader for standards.yaml — the project-standards file codegen and the critic consult
(BRIEF §10). Domain semantics live here, not in generated code: an "M8 clearance hole" is ⌀9.0.

PyYAML is imported lazily inside load() so importing this module never hard-fails before the
dependency is present.
"""
from __future__ import annotations

import functools
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PATH = _ROOT / "standards.yaml"


@functools.lru_cache(maxsize=1)
def load() -> dict:
    import yaml  # noqa: PLC0415  (lazy)
    with open(_PATH) as f:
        return yaml.safe_load(f)


def clearance_hole_mm(spec: str) -> float:
    """Drilled clearance diameter for a thread spec, e.g. 'M8' -> 9.0 (ISO 273 medium)."""
    return float(load()["clearance_holes_mm"][spec])


def tol_linear() -> float:
    """The dimensional critic's 'exact' tolerance (mm)."""
    return float(load()["tolerances"]["linear"])


def bbox_gate() -> float:
    """The P0 spine bbox gate: declared dims must match within this (mm)."""
    return float(load()["tolerances"]["bbox_gate"])


def cover_mm() -> float:
    """Concrete cover to a cast-in anchor (mm)."""
    return float(load()["manufacturing"]["cover_mm"])


def min_wall_mm() -> float:
    """Minimum wall thickness heuristic (mm)."""
    return float(load()["manufacturing"]["min_wall_mm"])


def drawing() -> dict:
    """The conventioned drawing conventions (sheet, scales, line weights, title block).
    Returns {} if the section is absent so the engine can fall back to built-in defaults."""
    return dict(load().get("drawing", {}) or {})
