"""Command line: `ludwig check`, `serve`, `user`, `purge`.

`check` exits 0 without blockers, 1 with blockers; any command exits 2 on a usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ludwig import check as checking
from ludwig.model import Severity
from ludwig.rules.packs import PackError, load_pack

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from ludwig.api.settings import Settings

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


def _service_db() -> tuple[Settings, sessionmaker]:
    try:
        from ludwig.api.db import connect
        from ludwig.api.settings import Settings
    except ImportError:
        raise UsageError("this needs: pip install 'ludwig[api]'") from None
    settings = Settings.from_env()
    return settings, connect(settings.database_url)


def _new_password() -> str:
    import getpass
    import os

    given = os.environ.get("LUDWIG_NEW_PASSWORD")
    if given:
        return given
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Again: "):
        raise UsageError("the passwords differ")
    return first


def user(args: argparse.Namespace) -> int:
    """Add a user or set a password, on the database in LUDWIG_DATABASE_URL."""
    from ludwig.api import auth
    from ludwig.api.activity import log
    from ludwig.api.db import User, UserSession

    _, sessions = _service_db()
    with sessions() as session:
        try:
            if args.action == "add":
                made = auth.create_user(session, args.name, _new_password(), admin=args.admin)
                log(session, "command line", "user added", user=made.name, admin=made.is_admin)
                print(f"added {made.name}" + (" (admin)" if made.is_admin else ""))
            else:
                found = session.query(User).filter(User.name == args.name).first()
                if found is None:
                    raise UsageError(f"no user {args.name!r}")
                password = _new_password()
                auth.check_password(password)
                found.password_hash = auth.hash_password(password)
                session.query(UserSession).filter(UserSession.user_id == found.id).delete()
                log(session, "command line", "user changed", user=found.name,
                    changes=["password"])  # fmt: skip
                print(f"password set for {found.name}")
            session.commit()
        except ValueError as exc:
            raise UsageError(str(exc)) from None
    return EXIT_OK


def purge(args: argparse.Namespace) -> int:
    """Delete projects with no activity for the retention period."""
    from ludwig.api.data import purge_expired
    from ludwig.api.storage import Storage

    settings, sessions = _service_db()
    days = args.days or settings.retention_days
    if not days:
        raise UsageError("give --days or set LUDWIG_RETENTION_DAYS")
    with sessions() as session:
        gone = purge_expired(session, Storage(settings.storage_dir), days)
    print(f"deleted {len(gone)} projects" + (f": {gone}" if gone else ""))
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
    u = sub.add_parser("user", help="add a user or set a password (service database)")
    u.add_argument("action", choices=["add", "password"])
    u.add_argument("name")
    u.add_argument("--admin", action="store_true", help="may manage users")
    u.set_defaults(func=user)
    g = sub.add_parser("purge", help="delete projects older than the retention period")
    g.add_argument("--days", type=int, help="default: LUDWIG_RETENTION_DAYS")
    g.set_defaults(func=purge)
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
