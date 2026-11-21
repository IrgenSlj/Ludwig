"""Database tables (ARCHITECTURE section 5). Postgres in production; any SQLAlchemy URL works."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Engine, ForeignKey, String, Text, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created: Mapped[datetime] = mapped_column(default=_now)
    uploads: Mapped[list[Upload]] = relationship(back_populates="project")


class Upload(Base):
    """A stored file; `role` is architect, erp or mapping (a mapping names its file)."""

    __tablename__ = "upload"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int]
    for_upload_id: Mapped[int | None] = mapped_column(ForeignKey("upload.id"))
    created: Mapped[datetime] = mapped_column(default=_now)
    project: Mapped[Project] = relationship(back_populates="uploads")


class Run(Base):
    """One check: the uploads and pack it used, its status and its summary."""

    __tablename__ = "run"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    pack_name: Mapped[str] = mapped_column(String(100))
    pack_version: Mapped[str] = mapped_column(String(50))
    pack_hash: Mapped[str] = mapped_column(String(80))
    upload_ids: Mapped[list[int]] = mapped_column(JSON)
    upload_hashes: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(default=_now)
    finished: Mapped[datetime | None]
    # Display name of each file in the findings -> its upload id.
    files: Mapped[dict[str, int] | None] = mapped_column(JSON)
    findings: Mapped[list[FindingRow]] = relationship(back_populates="run")


class FindingRow(Base):
    """One finding of a run; `data` is the finding exactly as in report.json."""

    __tablename__ = "finding"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"), index=True)
    position: Mapped[int]
    rule_id: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    mark: Mapped[str | None] = mapped_column(String(100))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    run: Mapped[Run] = relationship(back_populates="findings")
    reviews: Mapped[list[Review]] = relationship(back_populates="finding", order_by="Review.id")


class Review(Base):
    """A person's decision on a finding: accept or dismiss, with a reason. Never edited;
    a new decision is a new row, the latest one counts."""

    __tablename__ = "review"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("finding.id"), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default="")
    created: Mapped[datetime] = mapped_column(default=_now)
    user_name: Mapped[str | None] = mapped_column(String(100))
    finding: Mapped[FindingRow] = relationship(back_populates="reviews")


class LimitChange(Base):
    """A change to a pack's limits: the values set and both file versions (in storage)."""

    __tablename__ = "limit_change"

    id: Mapped[int] = mapped_column(primary_key=True)
    pack_name: Mapped[str] = mapped_column(String(100), index=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON)
    old_sha256: Mapped[str] = mapped_column(String(64))
    new_sha256: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
    created: Mapped[datetime] = mapped_column(default=_now)
    user_name: Mapped[str | None] = mapped_column(String(100))


class User(Base):
    """A person who signs in. Passwords are stored as scrypt hashes only."""

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    is_admin: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    created: Mapped[datetime] = mapped_column(default=_now)


class UserSession(Base):
    """A signed-in browser. Only the sha256 of the cookie token is stored."""

    __tablename__ = "user_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    created: Mapped[datetime] = mapped_column(default=_now)
    expires: Mapped[datetime]


class Event(Base):
    """One line of the activity log. `project_id` has no foreign key: the log outlives
    nothing it names, a deleted project's lines are deleted with it."""

    __tablename__ = "event"

    id: Mapped[int] = mapped_column(primary_key=True)
    created: Mapped[datetime] = mapped_column(default=_now, index=True)
    user_name: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50))
    project_id: Mapped[int | None] = mapped_column(index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


MIGRATIONS = Path(__file__).parent / "migrations"
BASELINE = "0001"  # the schema of databases made before migrations existed


def migrate(engine: Engine) -> None:
    """Bring the database to the newest schema; a pre-migration database is stamped first."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "project" in tables and "alembic_version" not in tables:
            command.stamp(cfg, BASELINE)
        command.upgrade(cfg, "head")


def connect(url: str) -> sessionmaker:
    """A session factory on a database migrated to the newest schema."""
    args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=args)
    migrate(engine)
    return sessionmaker(engine, expire_on_commit=False)
