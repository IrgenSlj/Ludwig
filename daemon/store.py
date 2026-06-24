"""On-disk project folders: ``projects/<id>/`` holds the program + outputs.

The orchestrator (``ludwig.py``) writes into ``renders/``; the daemon copies the
winning artifacts into the project folder so each project is self-contained
(BRIEF.md §3 "on-disk project folders"). ``ludwig.py`` itself is untouched.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import db


def project_dir(project_id: str) -> Path:
    d = db.projects_root() / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_text(project_id: str, name: str, content: str) -> Path:
    dest = project_dir(project_id) / name
    dest.write_text(content)
    return dest


def copy_in(project_id: str, src: str | Path, name: str) -> Path | None:
    src = Path(src)
    if not src.exists():
        return None
    dest = project_dir(project_id) / name
    shutil.copy2(src, dest)
    return dest
