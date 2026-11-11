"""The canonical JSON result (SPEC section 8). Same inputs and pack give the same bytes."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import ludwig
from ludwig.model import ParseWarning
from ludwig.report import report_order
from ludwig.rules.engine import RunResult

SCHEMA_VERSION = 1


def to_dict(
    result: RunResult, pack_name: str, pack_version: str, warnings: list[ParseWarning]
) -> dict[str, Any]:
    """The report as plain data."""
    statuses = Counter(f.status.value for f in result.findings)
    fails = Counter(f.severity.value for f in result.findings if f.status.value == "fail")
    return {
        "schema_version": SCHEMA_VERSION,
        "ludwig_version": ludwig.__version__,
        "pack": {"name": pack_name, "version": pack_version},
        "summary": {
            "rules_run": result.rules_run,
            "elements_total": result.elements_total,
            "elements_covered": result.elements_covered,
            "not_checked": result.not_checked,
            "by_status": dict(sorted(statuses.items())),
            "fails_by_severity": dict(sorted(fails.items())),
            "parse_warnings": len(warnings),
        },
        "parse_warnings": [w.to_dict() for w in warnings],
        "findings": [f.to_dict() for f in report_order(result.findings)],
    }


def dumps(data: dict[str, Any]) -> str:
    """Serialise with a fixed layout so equal reports are equal bytes."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write(
    path: str | Path,
    result: RunResult,
    pack_name: str,
    pack_version: str,
    warnings: list[ParseWarning],
) -> Path:
    """Write report.json."""
    path = Path(path)
    path.write_text(dumps(to_dict(result, pack_name, pack_version, warnings)), encoding="utf-8")
    return path
