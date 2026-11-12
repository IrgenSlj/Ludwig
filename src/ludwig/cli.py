"""Command line: `ludwig check`. Exit 0 without blockers, 1 with blockers, 2 on a usage error."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ludwig import check as checking
from ludwig.model import Severity
from ludwig.rules.packs import PackError, load_pack

EXIT_OK, EXIT_BLOCKERS, EXIT_USAGE = 0, 1, 2


class UsageError(Exception):
    """A problem with the command line or its files, reported with exit code 2."""


def check(args: argparse.Namespace) -> int:
    """Run `ludwig check` and return the exit code."""
    if args.mapping and not args.erp:
        raise UsageError("--mapping needs --erp")
    try:
        pack = load_pack(args.pack)
    except PackError as exc:
        raise UsageError(f"pack: {exc}") from None
    try:
        outcome = checking.run(
            [Path(p) for p in args.architect],
            pack,
            Path(args.erp) if args.erp else None,
            Path(args.mapping) if args.mapping else None,
        )
    except checking.InputError as exc:
        raise UsageError(str(exc)) from None
    out = Path(args.out)
    checking.write_reports(out, outcome, pack)
    result, blockers = outcome.result, outcome.fails(Severity.BLOCKER)
    print(
        f"{result.elements_total} elements, {result.rules_run} rules: "
        f"{blockers} blockers, {outcome.fails(Severity.WARNING)} warnings, "
        f"{result.not_checked} not checked, {len(outcome.warnings)} parse warnings. "
        f"Report: {out}"
    )
    return EXIT_BLOCKERS if blockers else EXIT_OK


def serve(args: argparse.Namespace) -> int:
    """Run the service with settings from LUDWIG_* environment variables."""
    try:
        import uvicorn

        from ludwig.api.app import create_app
    except ImportError:
        raise UsageError("the service needs: pip install 'ludwig[api]'") from None
    uvicorn.run(create_app(), host=args.host, port=args.port)
    return EXIT_OK


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
        help="IFC and DXF (office mapping <name>.mapping.yaml optional), schedules "
        "(.xlsx/.csv/.pdf, <name>.mapping.yaml required)",
    )
    p.add_argument("--erp", metavar="FILE", help="production export (.xlsx/.csv)")
    p.add_argument(
        "--mapping", metavar="FILE", help="export mapping (default: <name>.mapping.yaml beside it)"
    )
    p.add_argument("--pack", required=True, metavar="DIR", help="rule pack folder")
    p.add_argument("--out", required=True, metavar="DIR", help="folder for the reports")
    p.set_defaults(func=check)
    s = sub.add_parser("serve", help="run the HTTP service (needs the api extra)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=serve)
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
