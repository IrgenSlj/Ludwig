"""Run a pack's rules over the element table (SPEC sections 6 and 7). Reads no files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ludwig.model import Element, Finding, Match, MatchStatus, Side, SourceRef, Status
from ludwig.rules.expr import NotChecked
from ludwig.rules.packs import Pack, Rule, RuleKind

_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_LIMIT_NAME = re.compile(r"\blimits(?:\.[A-Za-z_][A-Za-z0-9_]*)+")


@dataclass
class RunResult:
    """Findings plus the coverage numbers every report states."""

    findings: list[Finding]
    rules_run: int
    elements_total: int
    elements_covered: int
    not_checked: int = field(init=False)

    def __post_init__(self) -> None:
        self.not_checked = sum(f.status is Status.NOT_CHECKED for f in self.findings)

    def extended(self, findings: list[Finding], rules: int) -> RunResult:
        """This result plus findings from `rules` more checks (IDS specifications)."""
        merged = [*self.findings, *findings]
        looked = [f for f in merged if f.status is not Status.NOT_APPLICABLE]
        covered = {i for f in looked for i in f.element_ids}
        return RunResult(merged, self.rules_run + rules, self.elements_total, len(covered))


def format_value(value: Any) -> str:
    """A value as shown in messages: 1200.0 -> '1200', None -> 'not set'."""
    if value is None:
        return "not set"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:g}"
    return str(value)


class _Scope:
    """Name lookup for one element: fields, props, limits and the parent element."""

    def __init__(self, element: Element, pack: Pack, by_id: dict[str, Element]):
        self.element = element
        self.pack = pack
        self.parent = by_id.get(element.parent_id) if element.parent_id else None

    def __call__(self, name: str) -> Any:
        if name.startswith("limits."):
            return self.pack.limit(name[len("limits.") :])
        element = self.element
        if name.startswith("parent."):
            if self.parent is None:
                return None
            element, name = self.parent, name[len("parent.") :]
        if name.startswith("props."):
            return element.props.get(name[len("props.") :])
        value = getattr(element, name)
        return value.value if hasattr(value, "value") else value

    def sources(self, name: str) -> list[SourceRef]:
        if name.startswith("limits."):
            return []
        element = self.element
        if name.startswith("parent."):
            if self.parent is None:
                return []
            element, name = self.parent, name[len("parent.") :]
        return element.sources_of(name)


def _render(template: str, scope: _Scope, extra: dict[str, Any]) -> str:
    def sub(match: re.Match) -> str:
        name = match.group(1)
        return format_value(extra[name] if name in extra else scope(name))

    return _PLACEHOLDER.sub(sub, template)


def _evidence(scope: _Scope, names: list[str]) -> list[SourceRef]:
    out: list[SourceRef] = []
    for name in names:
        for src in scope.sources(name):
            if src not in out:
                out.append(src)
    return out


def _run_require(rule: Rule, pack: Pack, elements: list[Element], by_id: dict) -> list[Finding]:
    findings = []
    expected = _LIMIT_NAME.sub(
        lambda m: format_value(pack.limit(m.group()[len("limits.") :])), rule.require.text
    )
    for el in elements:
        if not rule.applies_to(el.side, el.type):
            continue
        scope = _Scope(el, pack, by_id)
        base = dict(
            rule_id=rule.id,
            pack=pack.name,
            pack_version=pack.version,
            severity=rule.severity,
            element_ids=[el.id],
            mark=el.mark,
            expected=expected,
        )
        if rule.when is not None:
            gate = rule.when.evaluate(scope)
            if isinstance(gate.value, NotChecked) or not isinstance(gate.value, bool):
                nc = gate.value if isinstance(gate.value, NotChecked) else None
                reason = nc.reason if nc else "not true/false"
                findings.append(
                    Finding(
                        **base,
                        status=Status.NOT_CHECKED,
                        reason=f"when: {reason}",
                        evidence=_evidence(scope, gate.used),
                        message=f"{rule.id}: cannot tell whether it applies ({reason})",
                    )
                )
                continue
            if not gate.value:
                findings.append(Finding(**base, status=Status.NOT_APPLICABLE))
                continue

        result = rule.require.evaluate(scope)
        read = [n for n in result.used if not n.startswith("limits.")]
        values = {n: scope(n) for n in read}
        measured = values[read[0]] if len(read) == 1 else values
        if isinstance(result.value, NotChecked):
            status, reason = Status.NOT_CHECKED, result.value.reason
        elif isinstance(result.value, bool):
            status, reason = (Status.PASS if result.value else Status.FAIL), None
        else:
            status, reason = Status.NOT_CHECKED, "require did not give true or false"
        if status is Status.NOT_CHECKED:
            message = f"{rule.id}: not checked, {reason}"
        else:
            template = rule.message or f"{rule.id}: {{measured}}, expected {expected}"
            message = _render(template, scope, {"measured": measured, "expected": expected})
        findings.append(
            Finding(
                **base,
                status=status,
                measured=measured,
                message=message,
                evidence=_evidence(scope, result.used),
                reason=reason,
            )
        )
    return findings


def _values_agree(values: list[Any], tolerance: float) -> bool:
    numbers = [v for v in values if isinstance(v, int | float) and not isinstance(v, bool)]
    if len(numbers) == len(values):
        return max(numbers) - min(numbers) <= tolerance
    return len({format_value(v) for v in values}) == 1


def _run_consistent(rule: Rule, pack: Pack, elements: list[Element], by_id: dict) -> list:
    """One finding per group: the field must agree across the architect's documents.

    `quantity` is compared as a total per document; a document that has elements in this
    rule's scope but none in the group counts 0. Other fields must take one value per group.
    """
    base = dict(rule_id=rule.id, pack=pack.name, pack_version=pack.version, severity=rule.severity)
    findings: list[Finding] = []
    groups: dict[str, list[Element]] = {}
    documents: list[str] = []
    for el in elements:
        if not rule.applies_to(el.side, el.type):
            continue
        scope = _Scope(el, pack, by_id)
        if rule.when is not None:
            gate = rule.when.evaluate(scope)
            if isinstance(gate.value, NotChecked):
                reason = f"when: {gate.value.reason}"
                findings.append(Finding(**base, status=Status.NOT_CHECKED, element_ids=[el.id],
                                        mark=el.mark, reason=reason,
                                        message=f"{rule.id}: not checked, {reason}"))  # fmt: skip
                continue
            if gate.value is not True:
                continue
        doc = el.sources[0].file
        if doc not in documents:
            documents.append(doc)
        key = scope(rule.group_by)
        if key is None:
            reason = f"{rule.group_by} is not set"
            findings.append(Finding(**base, status=Status.NOT_CHECKED, element_ids=[el.id],
                                    reason=reason, evidence=list(el.sources[:1]),
                                    message=f"{rule.id}: not checked, {reason}"))  # fmt: skip
            continue
        groups.setdefault(format_value(key), []).append(el)

    expected = (
        "same total in every document"
        if rule.field == "quantity"
        else "one value" + (f" (within {format_value(rule.tolerance)})" if rule.tolerance else "")
    )
    for key, members in groups.items():
        scope = _Scope(members[0], pack, by_id)
        evidence: list[SourceRef] = []
        for el in members:
            for src in el.sources if rule.field == "quantity" else el.sources_of(rule.field):
                if src not in evidence:
                    evidence.append(src)
        group = dict(
            **base,
            element_ids=[el.id for el in members],
            mark=key if rule.group_by == "mark" else members[0].mark,
            expected=expected,
            evidence=evidence,
        )
        missing = [el for el in members if _Scope(el, pack, by_id)(rule.field) is None]
        if missing:
            files = ", ".join(sorted({el.sources[0].file for el in missing}))
            reason = f"{rule.field} is not set in {files}"
            findings.append(Finding(**group, status=Status.NOT_CHECKED, reason=reason,
                                    message=f"{rule.id} {key}: not checked, {reason}"))  # fmt: skip
            continue

        per_doc: dict[str, Any] = {}
        if rule.field == "quantity":
            for doc in documents:
                per_doc[doc] = sum(el.quantity for el in members if el.sources[0].file == doc)
            compared = list(per_doc.values())
            if len(documents) < 2:
                findings.append(Finding(**group, status=Status.NOT_APPLICABLE, measured=per_doc))
                continue
        else:
            compared = []
            raw_per_doc: dict[str, list[Any]] = {}
            for el in members:
                value = _Scope(el, pack, by_id)(rule.field)
                compared.append(value)
                raw_per_doc.setdefault(el.sources[0].file, []).append(value)
            for doc, values in raw_per_doc.items():
                distinct = sorted(set(values), key=format_value)
                per_doc[doc] = distinct if len(distinct) > 1 else distinct[0]
        ok = _values_agree(compared, rule.tolerance)
        if ok:
            message = ""
        else:
            shown = ", ".join(f"{Path(d).name} {_show(v)}" for d, v in per_doc.items())
            default = f"{rule.group_by} {key}: {rule.field} differs: {shown}"
            message = (
                _render(rule.message, scope, {"measured": shown, "expected": expected})
                if rule.message
                else default
            )
        findings.append(Finding(**group, status=Status.PASS if ok else Status.FAIL,
                                measured=per_doc, message=message))  # fmt: skip
    return findings


def _per_doc_text(per_doc: dict[str, Any]) -> str:
    """Values per document for a message; one value when every document agrees."""
    texts = {d: _show(v) for d, v in per_doc.items()}
    if len(set(texts.values())) == 1:
        return next(iter(texts.values()))
    return ", ".join(f"{Path(d).name} {v}" for d, v in texts.items())


def _show(value: Any) -> str:
    if isinstance(value, list):
        return " / ".join(format_value(v) for v in value)
    if isinstance(value, dict):
        return " / ".join(f"{k} x{format_value(n)}" for k, n in value.items())
    return format_value(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass
class _SideValues:
    """One side of a compare: per document, quantity per stated value (or the total)."""

    counts: dict[str, dict[Any, int]]
    missing: list[Element]
    partial: set[str]  # documents where some element does not state the value

    def values(self) -> list[Any]:
        """Every distinct value stated on this side."""
        out: list[Any] = []
        for counts in self.counts.values():
            out.extend(v for v in counts if v not in out)
        return out

    def shown(self) -> dict[str, Any]:
        """Per document: the single value, else {value: quantity}."""
        out: dict[str, Any] = {}
        for doc, counts in self.counts.items():
            if len(counts) == 1:
                out[doc] = next(iter(counts))
            else:
                out[doc] = {format_value(v): n for v, n in sorted(counts.items(),
                            key=lambda kv: format_value(kv[0]))}  # fmt: skip
        return out


def _side_values(members: list[Element], name: str, pack: Pack, by_id: dict) -> _SideValues:
    counts: dict[str, dict[Any, int]] = {}
    missing: list[Element] = []
    partial: set[str] = set()
    for el in members:
        doc = el.sources[0].file
        value = _Scope(el, pack, by_id)(name)
        if value is None:
            missing.append(el)
            partial.add(doc)
            continue
        if name == "quantity":
            total = counts.setdefault(doc, {0: 0})
            counts[doc] = {next(iter(total)) + value: 1}
            continue
        if el.quantity is None:
            partial.add(doc)
        per_value = counts.setdefault(doc, {})
        per_value[value] = per_value.get(value, 0) + (el.quantity or 0)
    return _SideValues(counts, missing, partial)


def _same(a: Any, b: Any, tolerance: float) -> bool | None:
    """Two values agree; None when one is a number and the other is not."""
    if _is_number(a) and _is_number(b):
        return abs(a - b) <= tolerance
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().casefold() == b.strip().casefold()
    return None


def _agree(left: _SideValues, right: _SideValues, tolerance: float) -> bool | None:
    """Each side's values have a counterpart on the other side; with several text values,
    every complete document also holds them in the same quantities. None: not comparable."""
    lv, rv = left.values(), right.values()
    for xs, ys in ((lv, rv), (rv, lv)):
        for x in xs:
            found = [_same(x, y, tolerance) for y in ys]
            if None in found:
                return None
            if not any(found):
                return False
    if len(lv) > 1 or len(rv) > 1:
        texts = [v for v in lv + rv if isinstance(v, str)]
        if len(texts) == len(lv) + len(rv):
            spreads = []
            for side in (left, right):
                for doc, counts in side.counts.items():
                    if doc in side.partial:
                        continue
                    spread: dict[str, int] = {}
                    for value, n in counts.items():
                        key = value.strip().casefold()
                        spread[key] = spread.get(key, 0) + n
                    spreads.append(spread)
            if any(s != spreads[0] for s in spreads):
                return False
    return True


def _no_production_data(rule: Rule, pack: Pack) -> Finding:
    reason = "no production data given"
    return Finding(rule_id=rule.id, pack=pack.name, pack_version=pack.version,
                   status=Status.NOT_CHECKED, severity=rule.severity, element_ids=[],
                   message=f"{rule.id}: not checked, {reason}", reason=reason)  # fmt: skip


def _match_evidence(m: Match) -> list[SourceRef]:
    out: list[SourceRef] = []
    for el in m.elements:
        for src in el.sources:
            if src not in out:
                out.append(src)
    return out


def _describe(m: Match) -> str:
    """How a position is named in messages: its mark, else its size and location."""
    if m.mark:
        return f"mark {m.mark}"
    el = m.elements[0]
    size = f"{format_value(el.width_mm)} x {format_value(el.height_mm)}"
    return f"unmarked {m.type.value} {size}" + (f" ({el.location})" if el.location else "")


def _ambiguous(rule: Rule, pack: Pack, m: Match) -> Finding:
    reason = (f"ambiguous match: {len(m.architect)} architect and {len(m.erp)} production "
              "elements fit each other")  # fmt: skip
    return Finding(rule_id=rule.id, pack=pack.name, pack_version=pack.version,
                   status=Status.NOT_CHECKED, severity=rule.severity,
                   element_ids=[e.id for e in m.elements], mark=m.mark, reason=reason,
                   evidence=_match_evidence(m),
                   message=f"{rule.id}: {_describe(m)}: not checked, {reason}")  # fmt: skip


def _run_unmatched(rule: Rule, pack: Pack, matches: list[Match] | None, by_id: dict) -> list:
    """One finding per position: pass when paired, fail when missing on `missing_on`."""
    if matches is None:
        return [_no_production_data(rule, pack)]
    missing = (MatchStatus.MISSING_IN_ERP if rule.missing_on is Side.ERP
               else MatchStatus.NOT_IN_ARCHITECT_SET)  # fmt: skip
    present = "architect set" if rule.missing_on is Side.ERP else "production data"
    absent = "production data" if rule.missing_on is Side.ERP else "architect set"
    expected = f"a counterpart in the {absent}"
    findings = []
    for m in matches:
        if rule.types and m.type not in rule.types:
            continue
        if m.status is MatchStatus.AMBIGUOUS:
            findings.append(_ambiguous(rule, pack, m))
            continue
        if m.status is not MatchStatus.MATCHED and m.status is not missing:
            continue
        ok = m.status is MatchStatus.MATCHED
        per_doc: dict[str, int] = {}
        for el in m.elements:
            doc = el.sources[0].file
            per_doc[doc] = per_doc.get(doc, 0) + (el.quantity or 0)
        quantity = next(iter(per_doc.values())) if len(set(per_doc.values())) == 1 else per_doc
        message = ""
        if not ok:
            count = _per_doc_text(per_doc)
            default = f"{_describe(m)}: in the {present} ({count}), not in the {absent}"
            scope = _Scope(m.elements[0], pack, by_id)
            extra = {"measured": f"{count} in the {present}", "expected": expected}
            message = _render(rule.message, scope, extra) if rule.message else default
        findings.append(Finding(rule_id=rule.id, pack=pack.name, pack_version=pack.version,
                                status=Status.PASS if ok else Status.FAIL,
                                severity=rule.severity, mark=m.mark,
                                element_ids=[e.id for e in m.elements],
                                measured=None if ok else {present: quantity, absent: 0},
                                expected=expected, message=message,
                                evidence=_match_evidence(m)))  # fmt: skip
    return findings


def _run_compare(rule: Rule, pack: Pack, matches: list[Match] | None, by_id: dict) -> list:
    """One finding per matched position: the architect value against the ERP value.

    The architect side uses the values its documents state (gaps between documents are the
    `consistent` rules' business); every ERP element must state the value.
    """
    if matches is None:
        return [_no_production_data(rule, pack)]
    left_side, left = rule.left.split(".", 1)
    right_side, right = rule.right.split(".", 1)
    tol = f" (within {format_value(rule.tolerance)})" if rule.tolerance else ""
    expected = f"{rule.left} == {rule.right}{tol}"
    findings = []
    for m in matches:
        if rule.types and m.type not in rule.types:
            continue
        if m.status is MatchStatus.AMBIGUOUS:
            findings.append(_ambiguous(rule, pack, m))
            continue
        if m.status is not MatchStatus.MATCHED:
            continue
        sides = {Side.ARCHITECT.value: m.architect, Side.ERP.value: m.erp}
        lmembers, rmembers = sides[left_side], sides[right_side]
        base = dict(rule_id=rule.id, pack=pack.name, pack_version=pack.version,
                    severity=rule.severity, mark=m.mark,
                    element_ids=[e.id for e in m.elements])  # fmt: skip
        if rule.when is not None:
            gates = [rule.when.evaluate(_Scope(el, pack, by_id)).value for el in m.elements]
            if True not in gates:
                unclear = next((g for g in gates if isinstance(g, NotChecked)), None)
                if unclear is None or False in gates:
                    findings.append(Finding(**base, status=Status.NOT_APPLICABLE))
                else:
                    reason = f"when: {unclear.reason}"
                    message = f"{rule.id}: not checked, {reason}"
                    findings.append(Finding(**base, status=Status.NOT_CHECKED, reason=reason,
                                            message=message))  # fmt: skip
                continue
        lside = _side_values(lmembers, left, pack, by_id)
        rside = _side_values(rmembers, right, pack, by_id)
        evidence: list[SourceRef] = []
        for el, name in [*((e, left) for e in lmembers), *((e, right) for e in rmembers)]:
            if _Scope(el, pack, by_id)(name) is None:
                continue  # an element that states nothing is no evidence
            for src in el.sources if name == "quantity" else el.sources_of(name):
                if src is not None and src not in evidence:
                    evidence.append(src)
        lshown, rshown = lside.shown(), rside.shown()
        if left == "quantity":
            lshown = {d: next(iter(c)) for d, c in lside.counts.items()}
        if right == "quantity":
            rshown = {d: next(iter(c)) for d, c in rside.counts.items()}
        base.update(expected=expected, evidence=evidence,
                    measured={rule.left: lshown, rule.right: rshown})  # fmt: skip
        reason = None
        if not lside.counts:
            reason = f"{rule.left} is not set"
        elif rside.missing or not rside.counts:
            files = ", ".join(sorted({Path(e.sources[0].file).name for e in rside.missing}))
            reason = f"{rule.right} is not set" + (f" in {files}" if files else "")
        ok = _agree(lside, rside, rule.tolerance) if reason is None else None
        if reason is None and ok is None:
            reason = "values of different kinds cannot be compared"
        if reason:
            message = f"{rule.id}: {_describe(m)}: not checked, {reason}"
            findings.append(Finding(**base, status=Status.NOT_CHECKED, reason=reason,
                                    message=message))  # fmt: skip
            continue
        shown = {rule.left: _per_doc_text(lshown), rule.right: _per_doc_text(rshown)}
        message = ""
        if not ok:
            both = f"{shown[rule.left]} vs {shown[rule.right]}"
            extra = {**shown, "expected": expected, "measured": both}
            scope = _Scope((lmembers or rmembers)[0], pack, by_id)
            message = (_render(rule.message, scope, extra) if rule.message
                       else f"{_describe(m)}: {left} differs: {both}")  # fmt: skip
        findings.append(Finding(**base, status=Status.PASS if ok else Status.FAIL,
                                message=message))  # fmt: skip
    return findings


def run(elements: list[Element], pack: Pack, matches: list[Match] | None = None) -> RunResult:
    """Run every rule over the elements, in pack order; `compare` rules use `matches`."""
    by_id = {el.id: el for el in elements}
    findings: list[Finding] = []
    for rule in pack.rules:
        if rule.kind is RuleKind.REQUIRE:
            findings.extend(_run_require(rule, pack, elements, by_id))
        elif rule.kind is RuleKind.CONSISTENT:
            findings.extend(_run_consistent(rule, pack, elements, by_id))
        elif rule.kind is RuleKind.UNMATCHED:
            findings.extend(_run_unmatched(rule, pack, matches, by_id))
        else:
            findings.extend(_run_compare(rule, pack, matches, by_id))
    covered = {i for f in findings if f.status is not Status.NOT_APPLICABLE for i in f.element_ids}
    return RunResult(findings, len(pack.rules), len(elements), len(covered))
