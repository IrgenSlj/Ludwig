"""IDS 1.0 specifications evaluated against the element table (PLAN 4.1).

IDS states what data must exist. Facets are checked against the raw IFC facts the IFC
parser keeps per occurrence (`Element.facts`), so no IFC file is opened here. Supported
facets: entity, attribute, property, classification, material, with simple values and
the restrictions enumeration, pattern, bounds and lengths. Anything else (partOf, other
restrictions, a pattern Python cannot read) gives `not_checked`, never a pass.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ludwig.model import Element, Finding, Severity, SourceRef, Status

IDS = "{http://standards.buildingsmart.org/IDS}"
XS = "{http://www.w3.org/2001/XMLSchema}"
FACETS = ("entity", "attribute", "property", "classification", "material", "partOf")
_BOUNDS = {"minInclusive": ">=", "maxInclusive": "<=", "minExclusive": ">", "maxExclusive": "<"}
_LENGTHS = ("length", "minLength", "maxLength")
# IDS gives measures in SI units; IFC files store them in project units.
_UNIT_POWER = {
    "IFCLENGTHMEASURE": 1, "IFCPOSITIVELENGTHMEASURE": 1, "IFCNONNEGATIVELENGTHMEASURE": 1,
    "IFCAREAMEASURE": 2, "IFCVOLUMEMEASURE": 3,
}  # fmt: skip


class IdsError(ValueError):
    """An IDS file that cannot be read."""


class Unsupported(Exception):
    """A facet or restriction this evaluator does not handle."""


@dataclass(frozen=True)
class Value:
    """An IDS value: a simple value or an xs:restriction."""

    simple: str | None = None
    enumeration: tuple[str, ...] = ()
    pattern: str | None = None
    bounds: tuple[tuple[str, float], ...] = ()
    lengths: tuple[tuple[str, int], ...] = ()
    unsupported: str | None = None

    def describe(self, quoted: bool = True) -> str:
        """Short text for messages; names are shown without quotes."""
        if self.simple is not None:
            return repr(self.simple) if quoted else self.simple
        parts = []
        if self.enumeration:
            parts.append("one of " + ", ".join(repr(v) for v in self.enumeration))
        if self.pattern is not None:
            parts.append(f"matching {self.pattern!r}")
        parts += [f"{op} {_num(n)}" for op, n in self.bounds]
        parts += [f"{kind} {n}" for kind, n in self.lengths]
        return " and ".join(parts) or "any value"

    def match(self, actual: Any) -> bool:
        """Whether a value satisfies this one; raises Unsupported when it cannot tell."""
        if self.unsupported:
            raise Unsupported(self.unsupported)
        if self.simple is not None:
            return _equal(actual, self.simple)
        if self.enumeration and not any(_equal(actual, v) for v in self.enumeration):
            return False
        if self.pattern is not None:
            try:
                if re.fullmatch(self.pattern, _text(actual)) is None:
                    return False
            except re.error as exc:
                raise Unsupported(f"pattern {self.pattern!r}: {exc}") from None
        for op, bound in self.bounds:
            number = _number(actual)
            if number is None or not _compare(number, op, bound):
                return False
        for kind, n in self.lengths:
            size = len(_text(actual))
            if (kind == "length" and size != n) or (kind == "minLength" and size < n) or (
                kind == "maxLength" and size > n
            ):
                return False
        return True


@dataclass(frozen=True)
class Facet:
    """One IDS facet with its parameters."""

    kind: str
    params: dict[str, Value] = field(default_factory=dict)
    data_type: str | None = None
    cardinality: str = "required"

    def describe(self) -> str:
        """Short text for messages."""
        p = self.params
        if self.kind == "entity":
            text = f"entity {p['name'].describe(False)}"
            if "predefinedType" in p:
                text += f" of type {p['predefinedType'].describe()}"
            return text
        if self.kind == "attribute":
            text = f"attribute {p['name'].describe(False)}"
        elif self.kind == "property":
            text = f"property {p['propertySet'].describe(False)}.{p['baseName'].describe(False)}"
        elif self.kind == "classification":
            text = "classification"
            if "system" in p:
                text += f" in {p['system'].describe(False)}"
        else:
            text = self.kind
        return text + (f" = {p['value'].describe()}" if "value" in p else "")


@dataclass
class Specification:
    """One IDS specification."""

    name: str
    index: int
    applicability: list[Facet]
    requirements: list[Facet]
    min_occurs: int = 0
    max_occurs: int | None = None
    description: str = ""


# Reading


def _value(node: ET.Element | None) -> Value | None:
    if node is None:
        return None
    simple = node.find(f"{IDS}simpleValue")
    if simple is not None:
        return Value(simple=(simple.text or "").strip())
    restriction = node.find(f"{XS}restriction")
    if restriction is None:
        raise IdsError(f"{node.tag}: needs simpleValue or xs:restriction")
    enumeration, pattern, bounds, lengths, unsupported = [], None, [], [], None
    for child in restriction:
        tag = child.tag.removeprefix(XS)
        raw = child.get("value", "")
        if tag == "enumeration":
            enumeration.append(raw)
        elif tag == "pattern":
            pattern = raw
        elif tag in _BOUNDS:
            number = _number(raw)
            if number is None:
                raise IdsError(f"xs:{tag} {raw!r} is not a number")
            bounds.append((_BOUNDS[tag], number))
        elif tag in _LENGTHS:
            lengths.append((tag, int(raw)))
        elif tag != "annotation":
            unsupported = f"restriction xs:{tag} is not supported"
    return Value(None, tuple(enumeration), pattern, tuple(bounds), tuple(lengths), unsupported)


def _facet(node: ET.Element) -> Facet:
    kind = node.tag.removeprefix(IDS)
    if kind not in FACETS:
        raise IdsError(f"unknown facet {kind!r}")
    if kind == "partOf":  # not evaluated; its nested entity is not read
        return Facet(kind, {}, None, node.get("cardinality", "required"))
    params = {}
    for child in node:
        name = child.tag.removeprefix(IDS)
        value = _value(child)
        if value is not None:
            params[name] = value
    required = {"entity": ["name"], "attribute": ["name"], "property": ["propertySet", "baseName"]}
    for name in required.get(kind, []):
        if name not in params:
            raise IdsError(f"{kind} facet needs {name}")
    data_type = node.get("dataType")
    return Facet(kind, params, data_type.upper() if data_type else None,
                 node.get("cardinality", "required"))  # fmt: skip


def load(path: str | Path) -> list[Specification]:
    """Read the specifications of an IDS 1.0 file; raises IdsError naming the problem."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise IdsError(f"{path}: {exc}") from None
    if root.tag != f"{IDS}ids":
        raise IdsError(f"{path}: not an IDS file (root {root.tag})")
    specs = []
    for i, node in enumerate(root.iter(f"{IDS}specification"), start=1):
        applicability = node.find(f"{IDS}applicability")
        requirements = node.find(f"{IDS}requirements")
        if applicability is None:
            raise IdsError(f"{path}: specification {i} has no applicability")
        max_occurs = applicability.get("maxOccurs", "unbounded")
        try:
            specs.append(Specification(
                name=node.get("name") or f"specification {i}",
                index=i,
                applicability=[_facet(f) for f in applicability],
                requirements=[_facet(f) for f in requirements] if requirements is not None else [],
                min_occurs=int(applicability.get("minOccurs", "0")),
                max_occurs=None if max_occurs == "unbounded" else int(max_occurs),
                description=node.get("description", ""),
            ))  # fmt: skip
        except (IdsError, ValueError) as exc:
            raise IdsError(f"{path}: specification {i}: {exc}") from None
    return specs


# Evaluating


def _num(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return _num(value)
    return str(value)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _equal(actual: Any, expected: str) -> bool:
    if isinstance(actual, int | float) and not isinstance(actual, bool):
        number = _number(expected)
        if number is not None:
            return math.isclose(actual, number, rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(actual, bool):
        return expected.strip().lower() == _text(actual)
    return _text(actual) == expected


def _compare(a: float, op: str, b: float) -> bool:
    return {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b}[op]


def _set(value: Any) -> bool:
    return value is not None and value != ""


def _check(facet: Facet, facts: dict[str, Any]) -> tuple[bool, bool, Any]:
    """(exists, satisfied, actual) of one facet on one occurrence; raises Unsupported."""
    p = facet.params
    if facet.kind == "entity":
        ok = p["name"].match(facts.get("entity", ""))
        if ok and "predefinedType" in p:
            ok = _set(facts.get("predefined_type")) and p["predefinedType"].match(
                facts["predefined_type"])  # fmt: skip
        return ok, ok, facts.get("entity")
    if facet.kind == "attribute":
        found = {k: v for k, v in facts.get("attributes", {}).items()
                 if p["name"].match(k) and _set(v)}  # fmt: skip
        return _found(found, p.get("value"), facet, facts)
    if facet.kind == "property":
        found = {}
        for pset, props in facts.get("properties", {}).items():
            if p["propertySet"].match(pset):
                found.update({f"{pset}.{k}": v for k, v in props.items()
                              if p["baseName"].match(k) and _set(v)})  # fmt: skip
        return _found(found, p.get("value"), facet, facts)
    if facet.kind == "classification":
        refs = [(s, c) for s, c in facts.get("classification", [])
                if "system" not in p or (s is not None and p["system"].match(s))]  # fmt: skip
        satisfied = bool(refs) and ("value" not in p or any(
            c is not None and p["value"].match(c) for _, c in refs))  # fmt: skip
        return bool(refs), satisfied, [c for _, c in refs] or None
    if facet.kind == "material":
        names = facts.get("material", [])
        satisfied = bool(names) and ("value" not in p or any(p["value"].match(n) for n in names))
        return bool(names), satisfied, names or None
    raise Unsupported(f"{facet.kind} facet is not supported")


def _found(found: dict, value: Value | None, facet: Facet, facts: dict) -> tuple[bool, bool, Any]:
    if not found:
        return False, False, None
    power = _UNIT_POWER.get(facet.data_type or "")
    scale = facts.get("unit_scale_m", 1.0) ** power if power else 1.0
    converted = {k: v * scale if power and _number(v) is not None else v for k, v in found.items()}
    satisfied = value is None or all(value.match(v) for v in converted.values())
    actual = next(iter(converted.values())) if len(converted) == 1 else converted
    return True, satisfied, actual


def _requirement_met(facet: Facet, facts: dict[str, Any]) -> tuple[bool, Any]:
    exists, satisfied, actual = _check(facet, facts)
    if facet.cardinality == "prohibited":
        return not satisfied, actual
    if facet.cardinality == "optional":
        return (not exists) or satisfied, actual
    return satisfied, actual


def rule_ids(specs: list[Specification]) -> list[str]:
    """A rule id per specification: `ids-<name>`, numbered when names repeat."""
    out: list[str] = []
    for spec in specs:
        slug = re.sub(r"[^a-z0-9]+", "-", spec.name.lower()).strip("-") or str(spec.index)
        rule_id = f"ids-{slug}"
        while rule_id in out:
            rule_id = f"ids-{slug}-{spec.index}"
        out.append(rule_id)
    return out


def run(specs: list[Specification], elements: list[Element], pack: str, version: str,
        severity: Severity = Severity.WARNING) -> list[Finding]:  # fmt: skip
    """Findings per specification: one per element with applicable occurrences, plus one
    for the specification's own occurrence limits."""
    with_facts = [el for el in elements if el.facts]
    findings: list[Finding] = []
    for spec, rule_id in zip(specs, rule_ids(specs), strict=True):
        base = dict(rule_id=rule_id, pack=pack, pack_version=version, severity=severity)
        expected = "; ".join(f"{f.cardinality} {f.describe()}" for f in spec.requirements)
        if not with_facts:
            reason = "no IFC model in the input"
            message = f"IDS '{spec.name}': not checked, {reason}"
            findings.append(Finding(**base, status=Status.NOT_CHECKED, element_ids=[],
                                    reason=reason, message=message))  # fmt: skip
            continue
        for el in with_facts:
            finding = _element(spec, el, base, expected)
            if finding is not None:
                findings.append(finding)
        findings.extend(_occurrences(spec, base, applicable_count(spec, with_facts)))
    return findings


def applicable_count(spec: Specification, elements: list[Element]) -> int | None:
    """How many occurrences the specification applies to; None when that cannot be told."""
    count = 0
    for el in elements:
        for facts in el.facts:
            try:
                if all(_check(f, facts)[1] for f in spec.applicability):
                    count += 1
            except Unsupported:
                return None
    return count


def _occurrences(spec: Specification, base: dict, count: int | None) -> list[Finding]:
    if spec.min_occurs == 0 and spec.max_occurs is None:
        return []
    limits = []
    if spec.min_occurs:
        limits.append(f"at least {spec.min_occurs}")
    if spec.max_occurs is not None:
        limits.append(f"at most {spec.max_occurs}")
    expected = " and ".join(limits) + " applicable elements"
    if count is None:
        reason = "applicability uses a facet that is not supported"
        message = f"IDS '{spec.name}': not checked, {reason}"
        return [Finding(**base, status=Status.NOT_CHECKED, element_ids=[], expected=expected,
                        reason=reason, message=message)]  # fmt: skip
    ok = count >= spec.min_occurs and (spec.max_occurs is None or count <= spec.max_occurs)
    message = "" if ok else f"IDS '{spec.name}': {count} applicable elements, expected {expected}"
    return [Finding(**base, status=Status.PASS if ok else Status.FAIL, element_ids=[],
                    measured=count, expected=expected, message=message)]  # fmt: skip


def _element(spec: Specification, el: Element, base: dict, expected: str) -> Finding | None:
    """The finding for one element, or None when no occurrence is applicable."""
    group = dict(**base, element_ids=[el.id], mark=el.mark, expected=expected)
    name = f"IDS '{spec.name}'" + (f", mark {el.mark}" if el.mark else "")
    applicable: list[SourceRef] = []
    failed: list[tuple[SourceRef, str]] = []
    try:
        for src, facts in zip(el.sources, el.facts, strict=True):
            if not all(_check(f, facts)[1] for f in spec.applicability):
                continue
            applicable.append(src)
            for facet in spec.requirements:
                ok, actual = _requirement_met(facet, facts)
                if not ok:
                    got = "missing" if actual is None else f"is {_shown(actual)}"
                    failed.append((src, f"{facet.cardinality} {facet.describe()}: {got}"))
    except Unsupported as exc:
        reason = str(exc)
        message = f"{name}: not checked, {reason}"
        return Finding(**group, status=Status.NOT_CHECKED, reason=reason,
                       evidence=list(el.sources), message=message)  # fmt: skip
    if not applicable:
        return None
    if not failed:
        return Finding(**group, status=Status.PASS, evidence=applicable)
    first = failed[0][1]
    bad = len({s for s, _ in failed})
    count = f" ({bad} of {len(applicable)} occurrences)" if len(applicable) > 1 else ""
    message = f"{name}: {first}{count}"
    evidence = list(dict.fromkeys(s for s, _ in failed))
    measured = {s.ifc_guid or s.file: text for s, text in failed}
    return Finding(**group, status=Status.FAIL, evidence=evidence, measured=measured,
                   message=message)  # fmt: skip


def _shown(actual: Any) -> str:
    if isinstance(actual, dict):
        return ", ".join(f"{k} {_text(v)!r}" for k, v in actual.items())
    if isinstance(actual, list):
        return ", ".join(repr(_text(v)) for v in actual)
    return repr(_text(actual))
