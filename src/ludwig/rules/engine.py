"""Run a pack's rules over the element table (SPEC sections 6 and 7). Reads no files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ludwig.model import Element, Finding, SourceRef, Status
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


def _unsupported(rule: Rule, pack: Pack) -> list[Finding]:
    reason = f"rule kind '{rule.kind}' is not supported yet"
    return [
        Finding(
            rule_id=rule.id,
            pack=pack.name,
            pack_version=pack.version,
            status=Status.NOT_CHECKED,
            severity=rule.severity,
            element_ids=[],
            message=f"{rule.id}: {reason}",
            reason=reason,
        )
    ]


def run(elements: list[Element], pack: Pack) -> RunResult:
    """Run every rule in the pack over the elements, in pack order then table order."""
    by_id = {el.id: el for el in elements}
    findings: list[Finding] = []
    for rule in pack.rules:
        if rule.kind is RuleKind.REQUIRE:
            findings.extend(_run_require(rule, pack, elements, by_id))
        else:
            findings.extend(_unsupported(rule, pack))
    covered = {i for f in findings if f.status is not Status.NOT_APPLICABLE for i in f.element_ids}
    return RunResult(findings, len(pack.rules), len(elements), len(covered))
