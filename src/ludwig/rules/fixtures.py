"""Per-rule fixtures (hard rule 3): pass.* must not fail the rule, fail.* must fail it."""

from __future__ import annotations

import json
from pathlib import Path

from ludwig.model import Element, Side, SourceKind, SourceRef, Status
from ludwig.rules import engine
from ludwig.rules.packs import Pack


def load_elements(path: Path) -> list[Element]:
    """A JSON fixture: {"elements": [...]}; id and sources may be left out."""
    data = json.loads(path.read_text())
    elements = []
    for i, raw in enumerate(data["elements"], start=1):
        raw = dict(raw)
        raw.setdefault("id", f"{path.name}#{i}")
        kind = SourceKind.ERP if raw.get("side") == Side.ERP.value else SourceKind.SHEET
        raw.setdefault("sources", [SourceRef(str(path), kind, cell=f"row {i}").to_dict()])
        elements.append(Element.from_dict(raw))
    return elements


def check(pack: Pack) -> list[str]:
    """Problems with the pack's fixtures; an empty list means every rule is covered."""
    problems = []
    for rule in pack.rules:
        folder = pack.root / "fixtures" / rule.id
        for case in ("pass", "fail"):
            files = sorted(folder.glob(f"{case}.*"))
            if not files:
                problems.append(f"{rule.id}: no {case} fixture")
                continue
            for path in files:
                if path.suffix != ".json":
                    problems.append(f"{rule.id}: {path.name}: only .json fixtures are supported")
                    continue
                result = engine.run(load_elements(path), pack)
                statuses = [f.status for f in result.findings if f.rule_id == rule.id]
                if case == "pass" and (Status.PASS not in statuses or Status.FAIL in statuses):
                    problems.append(f"{rule.id}: {path.name} should pass, got {statuses}")
                if case == "fail" and Status.FAIL not in statuses:
                    problems.append(f"{rule.id}: {path.name} should fail, got {statuses}")
    return problems
