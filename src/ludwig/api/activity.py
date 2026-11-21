"""Activity log (PLAN 6.6): who uploaded, ran, reviewed, changed limits or managed data, and when.

Lines name files and projects by id and file name only; no file content or finding values.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ludwig.api.db import Event, iso


def log(session: Session, actor: str | None, action: str, project_id: int | None = None,
        **detail: Any) -> None:  # fmt: skip
    """Add one line; the caller commits with its own change."""
    session.add(Event(user_name=actor, action=action, project_id=project_id, detail=detail))


def view(e: Event) -> dict[str, Any]:
    """An event as the API returns it."""
    return {"id": e.id, "created": iso(e.created), "user": e.user_name,
            "action": e.action, "project_id": e.project_id, "detail": e.detail}  # fmt: skip


def recent(session: Session, project_id: int | None = None, limit: int = 200) -> list[dict]:
    """Newest lines first, for one project or for everything."""
    rows = session.query(Event)
    if project_id is not None:
        rows = rows.filter(Event.project_id == project_id)
    return [view(e) for e in rows.order_by(Event.id.desc()).limit(min(limit, 1000))]
