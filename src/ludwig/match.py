"""Pair architect elements with ERP elements (SPEC section 5). Never changes an element."""

from __future__ import annotations

from dataclasses import dataclass

from ludwig.model import Element, ElementType, Match, MatchStatus, Side


@dataclass
class _Unit:
    """One position on one side: all elements of a type and mark, or one unmarked element."""

    side: Side
    type: ElementType
    mark: str | None
    elements: list[Element]

    def single(self, name: str) -> object:
        """The value every member shares, or None when it differs or is missing."""
        values = {getattr(el, name) for el in self.elements}
        return values.pop() if len(values) == 1 else None


def _units(elements: list[Element], side: Side) -> list[_Unit]:
    units: dict[tuple, _Unit] = {}
    for el in elements:
        if el.side is not side:
            continue
        key = (el.type, el.mark) if el.mark else (el.type, None, el.id)
        units.setdefault(key, _Unit(side, el.type, el.mark, [])).elements.append(el)
    return list(units.values())


def _location(unit: _Unit) -> str | None:
    value = unit.single("location")
    return value.strip().casefold() if isinstance(value, str) and value.strip() else None


def _candidates(a: _Unit, b: _Unit, tolerance: float) -> bool:
    """Fallback match: same type, same location when both state one, sizes within tolerance."""
    if a.type is not b.type or (a.mark and b.mark):
        return False
    la, lb = _location(a), _location(b)
    if la and lb and la != lb:
        return False
    for name in ("width_mm", "height_mm"):
        va, vb = a.single(name), b.single(name)
        if va is None or vb is None or abs(va - vb) > tolerance:
            return False
    return True


def _record(status: MatchStatus, arch: list[_Unit], erp: list[_Unit], by: str | None) -> Match:
    units = [*arch, *erp]
    marks = sorted({u.mark for u in units if u.mark})
    return Match(
        status=status,
        type=units[0].type,
        mark=marks[0] if len(marks) == 1 else None,
        architect=[el for u in arch for el in u.elements],
        erp=[el for u in erp for el in u.elements],
        by=by,
    )


def match(elements: list[Element], tolerance_mm: float = 0.0) -> list[Match]:
    """Pair by type and mark, then by type, location and size for units lacking a mark.

    One-to-one only: a fallback unit with more than one candidate, or whose candidate has
    another candidate, is ambiguous together with all of them.
    """
    arch, erp = _units(elements, Side.ARCHITECT), _units(elements, Side.ERP)
    out: list[Match] = []

    erp_by_mark = {(u.type, u.mark): u for u in erp if u.mark}
    left_arch, used = [], set()
    for unit in arch:
        other = erp_by_mark.get((unit.type, unit.mark)) if unit.mark else None
        if other is None:
            left_arch.append(unit)
            continue
        used.add(id(other))
        out.append(_record(MatchStatus.MATCHED, [unit], [other], "mark"))
    left_erp = [u for u in erp if id(u) not in used]

    # Connected groups of the candidate graph decide fallback matches.
    edges = {id(u): [] for u in [*left_arch, *left_erp]}
    for a in left_arch:
        for b in left_erp:
            if _candidates(a, b, tolerance_mm):
                edges[id(a)].append(b)
                edges[id(b)].append(a)
    seen: set[int] = set()
    for start in [*left_arch, *left_erp]:
        if id(start) in seen:
            continue
        group, todo = [], [start]
        seen.add(id(start))
        while todo:
            unit = todo.pop()
            group.append(unit)
            for nxt in edges[id(unit)]:
                if id(nxt) not in seen:
                    seen.add(id(nxt))
                    todo.append(nxt)
        a_units = [u for u in group if u.side is Side.ARCHITECT]
        e_units = [u for u in group if u.side is Side.ERP]
        if not e_units:
            out.append(_record(MatchStatus.MISSING_IN_ERP, a_units, [], None))
        elif not a_units:
            out.append(_record(MatchStatus.NOT_IN_ARCHITECT_SET, [], e_units, None))
        elif len(a_units) == len(e_units) == 1:
            out.append(_record(MatchStatus.MATCHED, a_units, e_units, "fallback"))
        else:
            out.append(_record(MatchStatus.AMBIGUOUS, a_units, e_units, None))

    def order(m: Match) -> tuple:
        return (m.type.value, m.mark or "", m.status.value, m.elements[0].id)

    return sorted(out, key=order)
