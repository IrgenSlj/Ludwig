"""Persistence — local SQLite (metadata, run history) + git-diffable recipe files (BRIEF §4).

The program/recipe on disk is the source of truth and the diffable record; SQLite holds metadata,
runs, candidates, and critic results. No opaque artifact is ever the primary record (principle #1).
Wired in P0/S5 alongside the CLI. Stub today.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS project (id TEXT PRIMARY KEY, name TEXT, created REAL);
CREATE TABLE IF NOT EXISTS run     (id TEXT PRIMARY KEY, project TEXT, brief TEXT, passed INTEGER, created REAL);
CREATE TABLE IF NOT EXISTS artifact(id TEXT PRIMARY KEY, run TEXT, kind TEXT, path TEXT);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn
