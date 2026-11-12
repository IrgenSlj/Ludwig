"""Command line: `ludwig check`. Exit 0 without blockers, 1 with blockers, 2 on a usage error."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ludwig.adapters import erp_table
from ludwig.match import pairs
from ludwig.model import Element, ParseWarning, Severity, Status
from ludwig.parsers import ifc, schedule
from ludwig.report import excel
from ludwig.report import json as json_report
from ludwig.rules import engine
from ludwig.rules.packs import PackError, load_pack

EXIT_OK, EXIT_BLOCKERS, EXIT_USAGE = 0, 1, 2
SCHEDULE_SUFFIXES = {".xlsx", ".xlsm", ".csv"}


class UsageError(Exception):
    """A problem with the command line or its files, reported with exit code 2."""


def _schedule_mapping(path: Path) -> Path:
    mapping = path.with_name(f"{path.stem}.mapping.yaml")
    if not mapping.exists():
        raise UsageError(f"{path}: no column mapping; expected {mapping.name} next to it")
    return mapping


def read_architect(files: list[Path]) -> tuple[list[Element], list[ParseWarning]]:
    """Parse every architect file by its extension."""
    elements: list[Element] = []
    warnings: list[ParseWarning] = []
    for path in files:
        if not path.is_file():
            raise UsageError(f"{path}: file not found")
        suffix = path.suffix.lower()
        if suffix == ".ifc":
            found, warned = ifc.parse(path)
        elif suffix in SCHEDULE_SUFFIXES:
            try:
                mapping = schedule.load_mapping(_schedule_mapping(path))
            except ValueError as exc:
                raise UsageError(str(exc)) from None
            found, warned = schedule.parse(path, mapping)
        else:
            raise UsageError(f"{path}: unsupported file type {suffix or '(none)'}")
        elements.extend(found)
        warnings.extend(warned)
    return elements, warnings


def read_erp(path: Path, mapping: Path | None) -> tuple[list[Element], list[ParseWarning]]:
    """Parse the production export with its mapping (default: <name>.mapping.yaml beside it)."""
    if not path.is_file():
        raise UsageError(f"{path}: file not found")
    if path.suffix.lower() not in SCHEDULE_SUFFIXES:
        raise UsageError(f"{path}: unsupported file type {path.suffix or '(none)'}")
    mapping = mapping or _schedule_mapping(path)
    if not mapping.is_file():
        raise UsageError(f"{mapping}: file not found")
    try:
        loaded = erp_table.load_mapping(mapping)
    except ValueError as exc:
        raise UsageError(str(exc)) from None
    return erp_table.parse(path, loaded)


def check(args: argparse.Namespace) -> int:
    """Run `ludwig check` and return the exit code."""
    if args.mapping and not args.erp:
        raise UsageError("--mapping needs --erp")
    try:
        pack = load_pack(args.pack)
    except PackError as exc:
        raise UsageError(f"pack: {exc}") from None
    elements, warnings = read_architect([Path(p) for p in args.architect])
    if args.erp:
        found, warned = read_erp(Path(args.erp), Path(args.mapping) if args.mapping else None)
        elements.extend(found)
        warnings.extend(warned)
    result = engine.run(elements, pack, pairs(elements, pack.match_tolerance_mm))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    json_path = json_report.write(out / "report.json", result, pack.name, pack.version, warnings)
    excel.write(out / "report.xlsx", result, pack.name, pack.version, warnings)

    def fails(severity: Severity) -> int:
        return sum(f.status is Status.FAIL and f.severity is severity for f in result.findings)

    blockers = fails(Severity.BLOCKER)
    print(
        f"{result.elements_total} elements, {result.rules_run} rules: "
        f"{blockers} blockers, {fails(Severity.WARNING)} warnings, "
        f"{result.not_checked} not checked, {len(warnings)} parse warnings. "
        f"Report: {json_path.parent}"
    )
    return EXIT_BLOCKERS if blockers else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for the `ludwig` command."""
    parser = argparse.ArgumentParser(prog="ludwig", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="check architect documents against a rule pack")
    p.add_argument(
        "--architect",
        nargs="+",
        required=True,
        metavar="FILE",
        help="IFC models and schedules (.xlsx/.csv with a <name>.mapping.yaml)",
    )
    p.add_argument("--erp", metavar="FILE", help="production export (.xlsx/.csv)")
    p.add_argument(
        "--mapping", metavar="FILE", help="export mapping (default: <name>.mapping.yaml beside it)"
    )
    p.add_argument("--pack", required=True, metavar="DIR", help="rule pack folder")
    p.add_argument("--out", required=True, metavar="DIR", help="folder for report.json/.xlsx")
    p.set_defaults(func=check)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the exit code."""
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except UsageError as exc:
        print(f"ludwig: error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
