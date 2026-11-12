"""One check: read the inputs, run the pack, write the reports. Used by the CLI and the API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ludwig.adapters import erp_table
from ludwig.match import pairs
from ludwig.model import Element, ParseWarning, Severity, Status
from ludwig.parsers import dxf, ifc, pdf, schedule
from ludwig.report import bcf, excel, pdf_markup
from ludwig.report import json as json_report
from ludwig.rules import engine, ids
from ludwig.rules.packs import Pack

SCHEDULE_SUFFIXES = {".xlsx", ".xlsm", ".csv"}


class InputError(ValueError):
    """An input that cannot be checked: missing file, unknown type, missing or bad mapping."""


def _schedule_mapping(path: Path) -> Path:
    mapping = path.with_name(f"{path.stem}.mapping.yaml")
    if not mapping.exists():
        raise InputError(f"{path}: no column mapping; expected {mapping.name} next to it")
    return mapping


def _optional_mapping(path: Path, load: Any) -> Any:
    """The office mapping `<name>.mapping.yaml` beside a drawing, else the default one."""
    mapping = path.with_name(f"{path.stem}.mapping.yaml")
    try:
        return load(mapping if mapping.exists() else None)
    except ValueError as exc:
        raise InputError(str(exc)) from None


def read_architect(files: list[Path]) -> tuple[list[Element], list[ParseWarning]]:
    """Parse every architect file by its extension."""
    elements: list[Element] = []
    warnings: list[ParseWarning] = []
    for path in files:
        if not path.is_file():
            raise InputError(f"{path}: file not found")
        suffix = path.suffix.lower()
        if suffix == ".ifc":
            found, warned = ifc.parse(path, _optional_mapping(path, ifc.load_mapping))
        elif suffix == ".dxf":
            found, warned = dxf.parse(path, _optional_mapping(path, dxf.load_mapping))
        elif suffix == ".pdf":
            try:
                mapping = pdf.load_mapping(_schedule_mapping(path))
            except ValueError as exc:
                raise InputError(str(exc)) from None
            found, warned = pdf.parse(path, mapping)
        elif suffix in SCHEDULE_SUFFIXES:
            try:
                mapping = schedule.load_mapping(_schedule_mapping(path))
            except ValueError as exc:
                raise InputError(str(exc)) from None
            found, warned = schedule.parse(path, mapping)
        elif suffix == ".dwg":
            raise InputError(f"{path}: DWG is not read directly; convert it to DXF first "
                             "(see docs/DWG.md)")  # fmt: skip
        else:
            raise InputError(f"{path}: unsupported file type {suffix or '(none)'}")
        elements.extend(found)
        warnings.extend(warned)
    return elements, warnings


def read_erp(path: Path, mapping: Path | None) -> tuple[list[Element], list[ParseWarning]]:
    """Parse the production export with its mapping (default: <name>.mapping.yaml beside it)."""
    if not path.is_file():
        raise InputError(f"{path}: file not found")
    if path.suffix.lower() not in SCHEDULE_SUFFIXES:
        raise InputError(f"{path}: unsupported file type {path.suffix or '(none)'}")
    mapping = mapping or _schedule_mapping(path)
    if not mapping.is_file():
        raise InputError(f"{mapping}: file not found")
    try:
        loaded = erp_table.load_mapping(mapping)
    except ValueError as exc:
        raise InputError(str(exc)) from None
    return erp_table.parse(path, loaded)


@dataclass
class Outcome:
    """What one check produced."""

    result: engine.RunResult
    warnings: list[ParseWarning]
    elements: list[Element]

    def fails(self, severity: Severity) -> int:
        """Failed findings of one severity."""
        return sum(f.status is Status.FAIL and f.severity is severity
                   for f in self.result.findings)  # fmt: skip


def run(architect: list[Path], pack: Pack, erp: Path | None = None,
        erp_mapping: Path | None = None) -> Outcome:  # fmt: skip
    """Parse the inputs and run every rule and IDS specification of the pack."""
    elements, warnings = read_architect(architect)
    if erp is not None:
        found, warned = read_erp(erp, erp_mapping)
        elements.extend(found)
        warnings.extend(warned)
    result = engine.run(elements, pack, pairs(elements, pack.match_tolerance_mm))
    if pack.ids_specs:
        found = ids.run(pack.ids_specs, elements, pack.name, pack.version, pack.ids_severity)
        result = result.extended(found, len(pack.ids_specs))
    return Outcome(result, warnings, elements)


def write_reports(out: Path, outcome: Outcome, pack: Pack, markup: bool = True) -> list[Path]:
    """Write report.json, report.xlsx, report.bcf and (unless told not to) marked PDFs."""
    out.mkdir(parents=True, exist_ok=True)
    meta = (pack.name, pack.version, outcome.warnings, pack.content_hash)
    written = [
        json_report.write(out / "report.json", outcome.result, *meta),
        excel.write(out / "report.xlsx", outcome.result, *meta),
        bcf.write(out / "report.bcf", outcome.result),
    ]
    return written + (pdf_markup.write(out, outcome.result) if markup else [])
