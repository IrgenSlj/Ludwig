"""Data controls for the pilot data agreement (PLAN 6.7, 6.8): delete or export a project,
and delete projects nobody has touched for the retention period."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from ludwig.api.activity import recent
from ludwig.api.db import Event, FindingRow, LimitChange, Project, Review, Run, Upload, iso
from ludwig.api.storage import Storage


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive(t: datetime) -> datetime:
    return t.astimezone(UTC).replace(tzinfo=None) if t.tzinfo else t


def delete_project(session: Session, storage: Storage, project: Project) -> dict[str, int]:
    """Remove a project with its files, runs, findings, reviews and activity lines.

    A stored file is removed when no other project's upload and no limit change uses it.
    """
    uploads = session.query(Upload).filter(Upload.project_id == project.id).all()
    runs = session.query(Run).filter(Run.project_id == project.id).all()
    run_ids = [r.id for r in runs]
    found = session.query(FindingRow.id).filter(FindingRow.run_id.in_(run_ids))
    finding_ids = [f for (f,) in found]
    counts = {"files": len(uploads), "runs": len(runs), "findings": len(finding_ids)}
    if finding_ids:
        session.query(Review).filter(Review.finding_id.in_(finding_ids)).delete()
        session.query(FindingRow).filter(FindingRow.id.in_(finding_ids)).delete()
    for run in runs:
        session.delete(run)
    # Mappings point at their files: delete them first.
    for upload in sorted(uploads, key=lambda u: u.role != "mapping"):
        session.delete(upload)
        session.flush()
    session.query(Event).filter(Event.project_id == project.id).delete()
    hashes = {u.sha256 for u in uploads}
    session.delete(project)
    session.commit()

    still_used = {h for (h,) in session.query(Upload.sha256).filter(Upload.sha256.in_(hashes))}
    for change in session.query(LimitChange):
        still_used |= {change.old_sha256, change.new_sha256}
    for digest in hashes - still_used:
        storage.object(digest).unlink(missing_ok=True)
    for run_id in run_ids:
        shutil.rmtree(storage.run_dir(run_id), ignore_errors=True)
    return counts


def export_project(session: Session, storage: Storage, project: Project) -> Path:
    """A zip of everything held for a project; the caller deletes the file after sending."""
    uploads = session.query(Upload).filter(Upload.project_id == project.id).order_by(Upload.id)
    runs = session.query(Run).filter(Run.project_id == project.id).order_by(Run.id).all()
    fd, name = tempfile.mkstemp(suffix=".zip")
    path = Path(name)
    with open(fd, "wb") as fh, zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(
            {"id": project.id, "name": project.name, "created": iso(project.created),
             "exported": _now().isoformat()}, indent=2))  # fmt: skip
        listing = []
        for u in uploads:
            arc = f"files/{u.id}-{u.filename}"
            obj = storage.object(u.sha256)
            if obj.is_file():
                zf.write(obj, arc)
            listing.append({"id": u.id, "role": u.role, "filename": u.filename, "file": arc,
                            "for_upload": u.for_upload_id, "sha256": u.sha256,
                            "created": iso(u.created)})  # fmt: skip
        zf.writestr("files.json", json.dumps(listing, indent=2))
        out_runs = []
        for run in runs:
            folder = storage.run_dir(run.id)
            if folder.is_dir():
                for report in sorted(folder.iterdir()):
                    if report.is_file():
                        zf.write(report, f"runs/{run.id}/{report.name}")
            findings = []
            for row in session.query(FindingRow).filter(FindingRow.run_id == run.id).order_by(
                FindingRow.position
            ):
                findings.append({**row.data, "reviews": [
                    {"decision": r.decision, "reason": r.reason, "by": r.user_name,
                     "created": iso(r.created)} for r in row.reviews]})  # fmt: skip
            out_runs.append({"id": run.id, "status": run.status, "error": run.error,
                             "pack": {"name": run.pack_name, "version": run.pack_version,
                                      "hash": run.pack_hash},
                             "uploads": run.upload_ids, "summary": run.summary,
                             "created": iso(run.created),
                             "findings": findings})  # fmt: skip
        zf.writestr("runs.json", json.dumps(out_runs, indent=2, default=str))
        zf.writestr("activity.json", json.dumps(recent(session, project.id, 1000), indent=2))
    return path


def last_activity(session: Session, project: Project) -> datetime:
    """The newest time anything happened in a project."""
    times = [_naive(project.created)]
    times += [_naive(t) for (t,) in session.query(Upload.created)
              .filter(Upload.project_id == project.id)]  # fmt: skip
    times += [_naive(t) for (t,) in session.query(Run.created).filter(Run.project_id == project.id)]
    times += [_naive(t) for (t,) in session.query(Event.created)
              .filter(Event.project_id == project.id)]  # fmt: skip
    times += [_naive(t) for (t,) in session.query(Review.created).join(FindingRow).join(Run)
              .filter(Run.project_id == project.id)]  # fmt: skip
    return max(times)


def purge_expired(session: Session, storage: Storage, days: int) -> list[int]:
    """Delete every project with no activity for `days` days; returns their ids."""
    cutoff = _now() - timedelta(days=days)
    gone = []
    for project in session.query(Project).all():
        if last_activity(session, project) < cutoff:
            pid = project.id
            delete_project(session, storage, project)
            gone.append(pid)
    if gone:
        session.add(Event(user_name="retention", action="projects deleted",
                          detail={"projects": gone, "days": days}))  # fmt: skip
        session.commit()
    return gone
