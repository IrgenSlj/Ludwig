"""SQLite project/run/artifact store for the Ludwig daemon (M0).

Stdlib ``sqlite3`` only — keeps the core dependency-light (BRIEF.md §3). Paths are
read from the environment at call time so tests can point them at a tmp dir:

    LUDWIG_DB        path to the sqlite file   (default: <repo>/ludwig.db)
    LUDWIG_PROJECTS  on-disk project folders   (default: <repo>/projects)

Schema is created lazily and idempotently on first connect per path.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

# Repo root = parent of this file's parent (daemon/ -> repo).
_ROOT = Path(__file__).resolve().parent.parent

_initialized: set[str] = set()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    slug        TEXT NOT NULL,
    brief       TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    mode        TEXT NOT NULL,
    params      TEXT NOT NULL,
    status      TEXT NOT NULL,
    score       REAL,
    critique    TEXT,
    error       TEXT,
    created_at  REAL NOT NULL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES runs(id),
    kind        TEXT NOT NULL,
    path        TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  REAL NOT NULL
);
"""


def db_path() -> str:
    return os.environ.get("LUDWIG_DB", str(_ROOT / "ludwig.db"))


def projects_root() -> Path:
    p = Path(os.environ.get("LUDWIG_PROJECTS", str(_ROOT / "projects")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def connect() -> sqlite3.Connection:
    path = db_path()
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if path not in _initialized:
        conn.executescript(_SCHEMA)
        conn.commit()
        _initialized.add(path)
    return conn


def _id() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- #
# writes
# --------------------------------------------------------------------------- #
def create_project(slug: str, brief: str) -> str:
    pid = _id()
    with connect() as c:
        c.execute(
            "INSERT INTO projects (id, slug, brief, created_at) VALUES (?,?,?,?)",
            (pid, slug, brief, time.time()),
        )
    return pid


def create_run(project_id: str, mode: str, params: dict) -> str:
    rid = _id()
    with connect() as c:
        c.execute(
            "INSERT INTO runs (id, project_id, mode, params, status, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (rid, project_id, mode, json.dumps(params), "running", time.time()),
        )
    return rid


def finish_run(run_id: str, *, status: str, score=None, critique=None, error=None) -> None:
    with connect() as c:
        c.execute(
            "UPDATE runs SET status=?, score=?, critique=?, error=?, finished_at=? "
            "WHERE id=?",
            (status, score, critique, error, time.time(), run_id),
        )


def add_artifact(run_id: str, kind: str, path: str) -> str:
    aid = _id()
    with connect() as c:
        c.execute(
            "INSERT INTO artifacts (id, run_id, kind, path, created_at) VALUES (?,?,?,?,?)",
            (aid, run_id, kind, str(path), time.time()),
        )
    return aid


# --------------------------------------------------------------------------- #
# reads
# --------------------------------------------------------------------------- #
def get_project(project_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return None
        project = dict(row)
        runs = []
        for r in c.execute(
            "SELECT * FROM runs WHERE project_id=? ORDER BY created_at", (project_id,)
        ).fetchall():
            run = dict(r)
            run["params"] = json.loads(run["params"])
            run["artifacts"] = [
                dict(a)
                for a in c.execute(
                    "SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at",
                    (run["id"],),
                ).fetchall()
            ]
            runs.append(run)
        project["runs"] = runs
        return project


def list_projects() -> list[dict]:
    with connect() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT * FROM projects ORDER BY created_at DESC"
            ).fetchall()
        ]


def get_artifact(artifact_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        return dict(row) if row else None
