"""The background job of a run: lay the uploads out as files, run the check, store results."""

from __future__ import annotations

import shutil
import tempfile
import traceback
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ludwig import check as checking
from ludwig.api.db import FindingRow, Run, Upload
from ludwig.api.storage import Storage
from ludwig.report import json as json_report
from ludwig.report import report_order
from ludwig.rules.packs import Pack


def _layout(session: Session, run: Run, storage: Storage, folder: Path) -> dict[str, list[Path]]:
    """Each file in its own folder under its own name, its mapping beside it."""
    uploads = {u.id: u for u in session.query(Upload).filter(Upload.id.in_(run.upload_ids))}
    paths: dict[int, Path] = {}
    for upload in sorted(uploads.values(), key=lambda u: u.id):
        if upload.role == "mapping":
            continue
        target = folder / str(upload.id) / upload.filename
        target.parent.mkdir(parents=True)
        shutil.copyfile(storage.object(upload.sha256), target)
        paths[upload.id] = target
    erp_mapping: Path | None = None
    for upload in uploads.values():
        if upload.role != "mapping":
            continue
        target_path = paths.get(upload.for_upload_id or -1)
        if target_path is None:
            raise checking.InputError(f"{upload.filename}: its file is not part of this run")
        mapping = target_path.with_name(f"{target_path.stem}.mapping.yaml")
        shutil.copyfile(storage.object(upload.sha256), mapping)
        if uploads[upload.for_upload_id].role == "erp":
            erp_mapping = mapping
    architect = [paths[i] for i, u in sorted(uploads.items()) if u.role == "architect"]
    erp = [paths[i] for i, u in sorted(uploads.items()) if u.role == "erp"]
    return {"architect": architect, "erp": erp, "erp_mapping": [erp_mapping] if erp_mapping else []}


def execute(run_id: int, sessions: sessionmaker, storage: Storage, pack: Pack) -> None:
    """Run one queued check to the end; any failure is recorded on the run, never raised."""
    with sessions() as session:
        run = session.get(Run, run_id)
        run.status = "running"
        session.commit()
        try:
            with tempfile.TemporaryDirectory(prefix="ludwig-run-") as tmp:
                files = _layout(session, run, storage, Path(tmp))
                if len(files["erp"]) > 1:
                    raise checking.InputError("a run takes at most one production export")
                outcome = checking.run(
                    files["architect"], pack,
                    files["erp"][0] if files["erp"] else None,
                    files["erp_mapping"][0] if files["erp_mapping"] else None,
                )  # fmt: skip
                checking.write_reports(storage.run_dir(run.id), outcome, pack)
            report = json_report.to_dict(outcome.result, pack.name, pack.version,
                                         outcome.warnings, pack.content_hash)  # fmt: skip
            for i, finding in enumerate(report_order(outcome.result.findings)):
                session.add(FindingRow(run_id=run.id, position=i, rule_id=finding.rule_id,
                                       status=finding.status.value, severity=finding.severity.value,
                                       mark=finding.mark, data=finding.to_dict()))  # fmt: skip
            run.summary = report["summary"]
            run.status = "done"
        except checking.InputError as exc:
            run.status, run.error = "failed", str(exc)
        except Exception:  # noqa: BLE001 - recorded for the operator, not shown in detail
            traceback.print_exc()
            run.status, run.error = "failed", "internal error; see the service log"
        run.finished = datetime.now(UTC)
        session.commit()
