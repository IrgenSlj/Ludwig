"""Excel report for the work preparer: one row per finding, blockers first."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ludwig.model import Finding, ParseWarning, Severity, Status
from ludwig.report import SEVERITY_ORDER, STATUS_ORDER, by_side, describe_source
from ludwig.rules.engine import RunResult, format_value

COLUMNS = (
    "Severity", "Status", "Mark", "Rule", "Message", "Drawings", "Production", "Expected",
    "Reason", "Drawings source", "Production source", "Elements",
)  # fmt: skip


def _measured(value: Any) -> Any:
    if isinstance(value, dict):
        if len(value) == 1 and not isinstance(next(iter(value.values())), dict):
            return _measured(next(iter(value.values())))  # one document: the value alone
        return ", ".join(f"{Path(str(k)).name}: {_text(v)}" for k, v in value.items())
    if isinstance(value, list):
        return " / ".join(format_value(v) for v in value)
    if isinstance(value, bool) or value is None or not isinstance(value, int | float):
        return format_value(value) if value is not None else None
    return value


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " / ".join(f"{k} x{format_value(n)}" for k, n in value.items())
    if isinstance(value, list):
        return " / ".join(format_value(v) for v in value)
    return format_value(value)


def _row(f: Finding) -> list[Any]:
    sides = by_side(f)
    return [
        f.severity.value,
        f.status.value,
        f.mark,
        f.rule_id,
        f.message,
        _measured(sides["values"]["architect"]),
        _measured(sides["values"]["erp"]),
        format_value(f.expected) if f.expected is not None else None,
        f.reason,
        "; ".join(describe_source(s) for s in sides["sources"]["architect"]) or None,
        "; ".join(describe_source(s) for s in sides["sources"]["erp"]) or None,
        ", ".join(f.element_ids),
    ]


def _sheet(wb: Any, title: str, header: tuple[str, ...], rows: list[list[Any]]) -> None:
    from openpyxl.styles import Font

    ws = wb.create_sheet(title)
    ws.append(list(header))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
        for cell in ws[ws.max_row]:
            # Values come from customer files; text must never become a formula.
            if isinstance(cell.value, str):
                cell.data_type = "s"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def write(
    path: str | Path,
    result: RunResult,
    pack_name: str,
    pack_version: str,
    warnings: list[ParseWarning],
    pack_hash: str | None = None,
) -> Path:
    """Write report.xlsx with Findings, Passed, Summary and Parse warnings sheets."""
    import openpyxl

    path = Path(path)
    open_items = [f for f in result.findings if f.status in (Status.FAIL, Status.NOT_CHECKED)]
    open_items.sort(key=lambda f: (SEVERITY_ORDER[f.severity], STATUS_ORDER[f.status]))
    passed = [f for f in result.findings if f.status is Status.PASS]

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Findings", COLUMNS, [_row(f) for f in open_items])
    _sheet(wb, "Passed", COLUMNS, [_row(f) for f in passed])

    def count(status: Status, severity: Severity | None = None) -> int:
        return sum(
            f.status is status and (severity is None or f.severity is severity)
            for f in result.findings
        )

    summary = [
        ["Pack", f"{pack_name} {pack_version}"],
        ["Pack hash", pack_hash],
        ["Rules run", result.rules_run],
        ["Elements", result.elements_total],
        ["Elements covered", result.elements_covered],
        ["Blockers", count(Status.FAIL, Severity.BLOCKER)],
        ["Warnings", count(Status.FAIL, Severity.WARNING)],
        ["Info", count(Status.FAIL, Severity.INFO)],
        ["Not checked", result.not_checked],
        ["Passed", count(Status.PASS)],
        ["Not applicable", count(Status.NOT_APPLICABLE)],
        ["Parse warnings", len(warnings)],
    ]
    _sheet(wb, "Summary", ("Item", "Value"), summary)
    wb.move_sheet("Summary", offset=-2)
    _sheet(
        wb,
        "Parse warnings",
        ("File", "Message", "Source"),
        [[w.file, w.message, describe_source(w.source) if w.source else None] for w in warnings],
    )
    wb.save(path)
    return path
