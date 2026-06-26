"""The pass-rate harness — Ludwig's one tracked number ([H6], BRIEF §10).

    first-pass geometric pass-rate = over the frozen held-out brief set, the fraction of briefs
    whose FIRST built IR passes the geometric gate (bbox matches declared dims within the gate
    tolerance, hole count matches, solid is valid). NO repair — this measures raw codegen reliability.

`run(builder)` takes any brief→Element builder (the reference oracle today; the LLM codegen at S3).
Needs the OCCT kernel (it materializes geometry); callers without cadquery should skip.
"""
from __future__ import annotations

from typing import Callable

from eval.briefs import BRIEFS
from geometry.service import GeometryService
from ir.elements import Element
from toolkit.standards import bbox_gate


def geometric_pass(el: Element, brief: dict, geom: GeometryService, tol: float) -> bool:
    d = brief["dims"]
    length, width, height = geom.bbox(el.geometry)
    # The middle (y) extent is declared as "width" for bar stock or "thickness" for a panel.
    extents = {"length": length, "width": width, "thickness": width, "height": height}
    bbox_ok = all(k in extents and abs(extents[k] - v) <= tol for k, v in d.items())
    holes_ok = geom.cylindrical_face_count(el.geometry) == brief["holes"]
    valid_ok = geom.is_valid(el.geometry)
    return bool(bbox_ok and holes_ok and valid_ok)


def run(builder: Callable[[dict], Element], briefs: list[dict] = BRIEFS):
    """Returns (rate, [(brief_id, passed), ...]). A build that raises counts as a fail (no repair)."""
    geom = GeometryService()
    tol = bbox_gate()
    results: list[tuple[str, bool]] = []
    for b in briefs:
        try:
            ok = geometric_pass(builder(b), b, geom, tol)
        except Exception:
            ok = False
        results.append((b["id"], ok))
    rate = sum(ok for _, ok in results) / len(results) if results else 0.0
    return rate, results
