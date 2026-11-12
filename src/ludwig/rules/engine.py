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

    def source(self, name: str) -> SourceRef | None:
        if name.startswith("limits."):
            return None
        element = self.element
        if name.startswith("parent."):
            if self.parent is None:
                return None
            element, name = self.parent, name[len("parent.") :]
        return element.source_of(name)


def _render(template: str, scope: _Scope, extra: dict[str, Any]) -> str:
    def sub(match: re.Match) -> str:
        name = match.group(1)
        return format_value(extra[name] if name in extra else scope(name))

    return _PLACEHOLDER.sub(sub, template)


def _evidence(scope: _Scope, names: list[str]) -> list[SourceRef]:
    out: list[SourceRef] = []
    for name in names:
        src = scope.source(name)
        if src is not None and src not in out:
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
            for src in el.sources if rule.field == "quantity" else [el.source_of(rule.field)]:
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


def _show(value: Any) -> str:
    if isinstance(value, list):
        return " / ".join(format_value(v) for v in value)
    return format_value(value)


def _side_values(
    members: list[Element], name: str, pack: Pack, by_id: dict
) -> tuple[dict[str, Any], list[Element]]:
    """Per document: the quantity total, or the distinct values; plus members lacking a value."""
    per_doc: dict[str, Any] = {}
    missing = []
    for el in members:
        value = _Scope(el, pack, by_id)(name)
        if value is None:
            missing.append(el)
            continue
        doc = el.sources[0].file
        if name == "quantity":
            per_doc[doc] = per_doc.get(doc, 0) + value
        else:
            values = per_doc.setdefault(doc, [])
            if value not in values:
                values.append(value)
    if name != "quantity":
        per_doc = {d: (sorted(v, key=format_value) if len(v) > 1 else v[0])
                   for d, v in per_doc.items()}  # fmt: skip
    return per_doc, missing


def _flat(per_doc: dict[str, Any]) -> list[Any]:
    return [x for v in per_doc.values() for x in (v if isinstance(v, list) else [v])]


def _agree(left: list[Any], right: list[Any], tolerance: float) -> bool | None:
    """Every left value against every right value; None when they cannot be compared."""
    for a in left:
        for b in right:
            numbers = all(isinstance(v, int | float) and not isinstance(v, bool) for v in (a, b))
            if numbers:
                if abs(a - b) > tolerance:
                    return False
            elif isinstance(a, str) and isinstance(b, str):
                if a.strip().casefold() != b.strip().casefold():
                    return False
            else:
                return None
    return True


def _run_compare(rule: Rule, pack: Pack, matches: list[Match] | None, by_id: dict) -> list:
    """One finding per matched position: the architect value against the ERP value.

    The architect side uses the values its documents state (gaps between documents are the
    `consistent` rules' business); every ERP element must state the value.
    """
    if matches is None:
        reason = "no production data given"
        return [Finding(rule_id=rule.id, pack=pack.name, pack_version=pack.version,
                        status=Status.NOT_CHECKED, severity=rule.severity, element_ids=[],
                        message=f"{rule.id}: not checked, {reason}", reason=reason)]  # fmt: skip
    left_side, left = rule.left.split(".", 1)
    right_side, right = rule.right.split(".", 1)
    tol = f" (within {format_value(rule.tolerance)})" if rule.tolerance else ""
    expected = f"{rule.left} == {rule.right}{tol}"
    findings = []
    for m in matches:
        if m.status is not MatchStatus.MATCHED or (rule.types and m.type not in rule.types):
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
                if unclear is None:
                    findings.append(Finding(**base, status=Status.NOT_APPLICABLE))
                else:
                    reason = f"when: {unclear.reason}"
                    message = f"{rule.id}: not checked, {reason}"
                    findings.append(Finding(**base, status=Status.NOT_CHECKED, reason=reason,
                                            message=message))  # fmt: skip
                continue
        lvals, _ = _side_values(lmembers, left, pack, by_id)
        rvals, rmissing = _side_values(rmembers, right, pack, by_id)
        evidence: list[SourceRef] = []
        for el, name in [*((e, left) for e in lmembers), *((e, right) for e in rmembers)]:
            for src in el.sources if name == "quantity" else [el.source_of(name)]:
                if src is not None and src not in evidence:
                    evidence.append(src)
        base.update(expected=expected, evidence=evidence,
                    measured={rule.left: lvals, rule.right: rvals})  # fmt: skip
        reason = None
        if not lvals:
            reason = f"{rule.left} is not set"
        elif rmissing or not rvals:
            files = ", ".join(sorted({Path(e.sources[0].file).name for e in rmissing}))
            reason = f"{rule.right} is not set" + (f" in {files}" if files else "")
        ok = _agree(_flat(lvals), _flat(rvals), rule.tolerance) if reason is None else None
        if reason is None and ok is None:
            reason = "values of different kinds cannot be compared"
        if reason:
            message = f"{rule.id}: mark {m.mark}: not checked, {reason}"
            findings.append(Finding(**base, status=Status.NOT_CHECKED, reason=reason,
                                    message=message))  # fmt: skip
            continue
        shown = {
            rule.left: ", ".join(f"{Path(d).name} {_show(v)}" for d, v in lvals.items()),
            rule.right: ", ".join(f"{Path(d).name} {_show(v)}" for d, v in rvals.items()),
        }
        message = ""
        if not ok:
            both = f"{shown[rule.left]} vs {shown[rule.right]}"
            extra = {**shown, "expected": expected, "measured": both}
            scope = _Scope((lmembers or rmembers)[0], pack, by_id)
            message = (_render(rule.message, scope, extra) if rule.message
                       else f"mark {m.mark}: {left} differs: {both}")  # fmt: skip
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
        else:
            findings.extend(_run_compare(rule, pack, matches, by_id))
    covered = {i for f in findings if f.status is not Status.NOT_APPLICABLE for i in f.element_ids}
    return RunResult(findings, len(pack.rules), len(elements), len(covered))
