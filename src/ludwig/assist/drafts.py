"""Drafts and explanations for a person to read (SPEC section 9). Nothing is saved here."""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from ludwig.model import ELEMENT_FIELDS, STANDARD_PROPS, ElementType, Finding
from ludwig.parsers import schedule
from ludwig.rules.packs import Pack, PackError, load_pack

_FENCE = re.compile(r"```(?:ya?ml)?\s*\n(.*?)```", re.S)


class Provider(Protocol):
    def complete(self, prompt: str) -> str: ...


@dataclass
class Draft:
    """A model's proposal: its text, and the problems found checking it (empty: it loads)."""

    text: str
    problems: list[str] = field(default_factory=list)
    note: str = "Draft only. A person reviews it; a rule needs pass and fail fixtures before use."


def _yaml_block(answer: str) -> str:
    match = _FENCE.search(answer)
    return (match.group(1) if match else answer).strip() + "\n"


RULE_FORMAT = """\
Rule format (YAML, one list item):
- id: lower-case-words-with-dashes
  kind: require            # or compare / consistent / unmatched
  applies_to: {side: architect|erp, type: <type>}
  when: <expression>       # optional filter
  require: <expression>    # must be true
  severity: blocker|warning|info
  message: "text with {mark}, {width_mm}, {limits.<path>} placeholders"
  description: one sentence for a person
Expression language: numbers, "strings", true, false; names; + - * /; == != < <= > >=;
and or not; in [a, b]; abs(x) min(a, b) max(a, b) is_set(x). Nothing else.
"""


def draft_rule(text: str, pack: Pack, provider: Provider) -> Draft:
    """Draft one rule from specification text; checked by loading the pack with it added."""
    limits = sorted(_limit_paths(pack.limits))
    examples = (pack.root / "checks.yaml").read_text()[:4000]
    prompt = (
        "You write one rule for Ludwig, a deterministic pre-production checker for joinery "
        "(windows, doors, frames). Answer with a single YAML block and nothing else.\n\n"
        f"{RULE_FORMAT}\n"
        f"Element types: {', '.join(t.value for t in ElementType)}\n"
        f"Fields: {', '.join(ELEMENT_FIELDS)} (lengths in mm)\n"
        f"Properties: {', '.join('props.' + p for p in sorted(STANDARD_PROPS))}\n"
        f"Limits available: {', '.join(limits) or 'none'}\n"
        "Use a limit instead of a number when one fits.\n\n"
        f"Existing rules in this pack:\n{examples}\n\n"
        f"Specification text:\n{text.strip()}\n"
    )
    rule = _yaml_block(provider.complete(prompt))
    return Draft(rule, _check_rule(rule, pack))


def _limit_paths(node: Any, prefix: str = "limits") -> set[str]:
    if isinstance(node, dict):
        return set().union(*(_limit_paths(v, f"{prefix}.{k}") for k, v in node.items()))
    return {prefix}


def _check_rule(rule: str, pack: Pack) -> list[str]:
    try:
        parsed = yaml.safe_load(rule)
    except yaml.YAMLError as exc:
        return [f"not valid YAML: {exc}"]
    if not (isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict)):
        return ["expected exactly one rule as a YAML list item"]
    with tempfile.TemporaryDirectory() as tmp:
        trial = Path(tmp) / "pack"
        shutil.copytree(pack.root, trial, ignore=shutil.ignore_patterns("fixtures"))
        checks = trial / "checks.yaml"
        checks.write_text(checks.read_text().rstrip() + "\n\n" + rule)
        try:
            load_pack(trial)
        except PackError as exc:
            return [str(exc).replace(str(trial) + "/", "")]
    return []


def suggest_mapping(
    headers: list[str], provider: Provider, sample: list[list[str]] | None = None
) -> Draft:
    """Propose a schedule/export column mapping for a person to confirm."""
    rows = "\n".join(" | ".join(r) for r in (sample or [])[:5])
    prompt = (
        "Map the columns of a joinery schedule or production export to Ludwig's fields. "
        "Answer with a single YAML block and nothing else, in this form:\n"
        "header_row: 1\ntype: frame\nunits: mm\ncolumns: {mark: <col>, quantity: <col>, "
        "width_mm: <col>, height_mm: <col>, location: <col>}\n"
        "props: {<name>: {column: <col>, as: number|text}}\n"
        f"Allowed props: {', '.join(sorted(STANDARD_PROPS))}. Leave out what has no column. "
        "Use header names exactly as given.\n\n"
        f"Headers: {' | '.join(headers)}\nFirst rows:\n{rows}\n"
    )
    text = _yaml_block(provider.complete(prompt))
    problems: list[str] = []
    try:
        mapping = yaml.safe_load(text)
        schedule.load_mapping_dict(mapping if isinstance(mapping, dict) else {}, "suggestion")
        given = {h.strip().lower() for h in headers}
        named = [c for c in mapping.get("columns", {}).values()]
        named += [s.get("column") for s in mapping.get("props", {}).values() if isinstance(s, dict)]
        problems += [f"column {c!r} is not in the headers" for c in named
                     if str(c).strip().lower() not in given]  # fmt: skip
    except (yaml.YAMLError, ValueError, AttributeError, TypeError) as exc:
        problems.append(str(exc))
    return Draft(text, problems, "Suggestion only. Confirm each column before saving the mapping.")


def explain(finding: Finding, provider: Provider) -> str:
    """The finding in plain words for a work preparer. The finding itself is unchanged."""
    prompt = (
        "Explain this pre-production check finding to a joinery work preparer in two or three "
        "plain sentences: what is wrong, where to look, what to ask the architect or fix in "
        "production. Do not judge whether the finding is right and do not invent values.\n\n"
        f"Message: {finding.message}\nRule: {finding.rule_id}\nStatus: {finding.status.value}\n"
        f"Severity: {finding.severity.value}\nMark: {finding.mark}\n"
        f"Measured: {finding.measured}\nExpected: {finding.expected}\nReason: {finding.reason}\n"
    )
    return provider.complete(prompt)
