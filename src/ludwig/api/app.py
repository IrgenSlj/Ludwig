"""FastAPI application: projects, uploads, runs and findings (PLAN 5.1)."""

from __future__ import annotations

import csv
import io
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ludwig.api import activity, auth, data, jobs, status
from ludwig.api.db import FindingRow, LimitChange, Project, Review, Run, Upload, connect, iso
from ludwig.api.guards import origin_ok
from ludwig.api.settings import Settings
from ludwig.api.storage import Storage
from ludwig.assist import drafts
from ludwig.assist.provider import AssistFailed, CommandProvider
from ludwig.model import Finding, Side, SourceRef
from ludwig.parsers import columns as table_columns
from ludwig.parsers import schedule
from ludwig.report import describe_source
from ludwig.rules import limits as pack_limits
from ludwig.rules.packs import Pack, PackError, load_pack

ROLES = ("architect", "erp", "mapping")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
REPORTS = {"report.json": "application/json", "report.bcf": "application/zip", "report.xlsx": XLSX}


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(accept|dismiss)$")
    reason: str = Field(default="", max_length=2000)


class LimitsIn(BaseModel):
    values: dict[str, float] = Field(min_length=1)
    reason: str = Field(default="", max_length=2000)


class RuleDraftIn(BaseModel):
    pack: str
    text: str = Field(min_length=1, max_length=20000)


class MappingDraftIn(BaseModel):
    headers: list[str] = Field(min_length=1, max_length=200)
    sample: list[list[str]] = Field(default_factory=list, max_length=5)


class MappingIn(BaseModel):
    mapping: dict[str, Any]
    save: bool = False


class RunIn(BaseModel):
    pack: str
    uploads: list[int] = Field(min_length=1)


# Sent with every response. The web app loads only its own files; page previews are blob:
# images; React sets style through the DOM, which style-src does not restrict.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}

PAGE_SCALE = 1.5  # image pixels per PDF point; boxes in evidence are in points


def render_page(pdf: Path, page: int) -> bytes | None:
    """One PDF page as PNG, or None when the page does not exist."""
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        if not 1 <= page <= len(doc.pages):
            return None
        image = doc.pages[page - 1].to_image(resolution=72 * PAGE_SCALE).original
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _packs(folder: Path) -> dict[str, Pack]:
    packs = {}
    for pack_file in sorted(folder.glob("*/pack.yaml")):
        try:
            pack = load_pack(pack_file.parent)
        except PackError:
            continue  # a broken pack is not offered; `ludwig check` names its error
        packs[pack.name] = pack
    return packs


def _project(p: Project) -> dict[str, Any]:
    return {"id": p.id, "name": p.name, "created": iso(p.created)}


def _upload(u: Upload) -> dict[str, Any]:
    return {"id": u.id, "project_id": u.project_id, "role": u.role, "filename": u.filename,
            "sha256": u.sha256, "size": u.size, "for_upload": u.for_upload_id}  # fmt: skip


def _run(r: Run) -> dict[str, Any]:
    return {"id": r.id, "project_id": r.project_id, "status": r.status, "error": r.error,
            "pack": {"name": r.pack_name, "version": r.pack_version, "hash": r.pack_hash},
            "uploads": r.upload_ids, "upload_hashes": r.upload_hashes, "summary": r.summary,
            "files": r.files or {},
            "created": iso(r.created),
            "finished": iso(r.finished) if r.finished else None}  # fmt: skip


def _review(r: Review | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {"decision": r.decision, "reason": r.reason, "by": r.user_name,
            "created": iso(r.created)}  # fmt: skip


def _finding(row: FindingRow) -> dict[str, Any]:
    return {"id": row.id, "run_id": row.run_id, **row.data,
            "review": _review(row.reviews[-1] if row.reviews else None)}  # fmt: skip


CSV_COLUMNS = ("id", "severity", "status", "mark", "rule_id", "message", "expected", "reason",
               "review", "review_reason", "sources")  # fmt: skip


def _safe_name(name: str | None) -> str:
    base = Path(name or "").name.strip()
    if not base or base in (".", "..") or len(base) > 255:
        raise HTTPException(422, "a file name is required")
    return base


def _db(request: Request) -> Any:
    with request.app.state.sessions() as session:
        yield session


DB = Annotated[Session, Depends(_db)]


def create_app(settings: Settings | None = None) -> FastAPI:
    """The service, with its database, storage and packs from `settings`."""
    settings = settings or Settings.from_env()
    sessions = connect(settings.database_url)
    storage = Storage(settings.storage_dir)
    app = FastAPI(title="Ludwig", version="0.1")
    app.state.sessions = sessions
    auth_routes, user_routes, require_user, require_admin = auth.router(settings, sessions)

    def who(request: Request) -> str | None:
        return getattr(request.state, "user_name", None)

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Any:
        # Sign-in is checked per route (auth.require_user); this refuses cross-site writes.
        if request.url.path.startswith("/api/"):
            if request.method not in ("GET", "HEAD", "OPTIONS") and not origin_ok(
                request.headers.get("origin"), request.headers.get("host"), settings.allowed_origins
            ):
                return JSONResponse({"detail": "cross-origin request refused"}, status_code=403,
                                    headers=SECURITY_HEADERS)  # fmt: skip
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    def project_or_404(session: Session, project_id: int) -> Project:
        project = session.get(Project, project_id)
        if project is None:
            raise HTTPException(404, "no such project")
        return project

    def run_or_404(session: Session, run_id: int) -> Run:
        run = session.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "no such run")
        return run

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    api = APIRouter(prefix="/api", dependencies=[Depends(require_user)])

    @api.get("/packs")
    def packs() -> list[dict[str, Any]]:
        return [{"name": p.name, "version": p.version, "hash": p.content_hash,
                 "description": p.description, "rules": len(p.rules) + len(p.ids_specs)}
                for p in _packs(settings.packs_dir).values()]  # fmt: skip

    def pack_or_404(name: str) -> Pack:
        pack = _packs(settings.packs_dir).get(name)
        if pack is None:
            raise HTTPException(404, f"no pack named {name!r}")
        return pack

    def pack_view(pack: Pack, session: Session) -> dict[str, Any]:
        changes = (session.query(LimitChange).filter(LimitChange.pack_name == pack.name)
                   .order_by(LimitChange.id.desc()).limit(20))  # fmt: skip
        return {
            "name": pack.name, "version": pack.version, "hash": pack.content_hash,
            "description": pack.description,
            "writable": os.access(pack.root / "limits.yaml", os.W_OK),
            "limits": [vars(x) for x in pack_limits.read(pack)],
            "rules": [{"id": r.id, "kind": r.kind.value, "severity": r.severity.value,
                       "description": r.description, "message": r.message} for r in pack.rules],
            "changes": [{"values": c.values, "reason": c.reason, "by": c.user_name,
                         "created": iso(c.created)} for c in changes],
        }  # fmt: skip

    @api.get("/packs/{name}")
    def get_pack(name: str, session: DB) -> dict[str, Any]:
        return pack_view(pack_or_404(name), session)

    @api.put("/packs/{name}/limits")
    def set_limits(name: str, body: LimitsIn, request: Request, session: DB) -> dict[str, Any]:
        pack = pack_or_404(name)
        path = pack.root / "limits.yaml"
        if not os.access(path, os.W_OK):
            raise HTTPException(409, "this pack is read-only here; edit limits.yaml on the server")
        old = storage.put(path.read_bytes())
        try:
            pack = pack_limits.update(pack, dict(body.values))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        session.add(LimitChange(pack_name=pack.name, values=dict(body.values), old_sha256=old,
                                new_sha256=storage.put(path.read_bytes()),
                                reason=body.reason.strip(), user_name=who(request)))  # fmt: skip
        activity.log(session, who(request), "limits changed", pack=pack.name,
                     values=dict(body.values))  # fmt: skip
        session.commit()
        return pack_view(pack, session)

    provider = CommandProvider(settings.assist_command) if settings.assist_command else None

    def assist() -> CommandProvider:
        if provider is None:
            raise HTTPException(409, "assist is off; set LUDWIG_ASSIST_COMMAND to enable it")
        return provider

    def assisted(call: Any) -> Any:
        try:
            return call()
        except AssistFailed as exc:
            raise HTTPException(502, str(exc)) from None

    @api.get("/assist")
    def assist_state() -> dict[str, bool]:
        return {"enabled": provider is not None}

    @api.post("/assist/explain/{finding_id}")
    def assist_explain(finding_id: int, session: DB) -> dict[str, Any]:
        model = assist()
        row = session.get(FindingRow, finding_id)
        if row is None:
            raise HTTPException(404, "no such finding")
        finding = Finding.from_dict(row.data)
        text = assisted(lambda: drafts.explain(finding, model))
        note = "Written by a language model from the finding; the finding is unchanged."
        return {"finding_id": row.id, "explanation": text, "original": row.data["message"],
                "note": note}  # fmt: skip

    @api.post("/assist/rule")
    def assist_rule(body: RuleDraftIn) -> dict[str, Any]:
        model = assist()
        pack = pack_or_404(body.pack)
        return vars(assisted(lambda: drafts.draft_rule(body.text, pack, model)))

    @api.post("/assist/mapping")
    def assist_mapping(body: MappingDraftIn) -> dict[str, Any]:
        return vars(assisted(lambda: drafts.suggest_mapping(body.headers, assist(), body.sample)))

    @api.post("/projects", status_code=201)
    def create_project(body: ProjectIn, request: Request, session: DB) -> dict[str, Any]:
        project = Project(name=body.name)
        session.add(project)
        session.flush()
        activity.log(session, who(request), "project created", project.id, name=project.name)
        session.commit()
        return _project(project)

    @api.get("/projects")
    def list_projects(session: DB) -> list[dict[str, Any]]:
        return [_project(p) for p in session.query(Project).order_by(Project.id)]

    @api.get("/projects/{project_id}")
    def get_project(project_id: int, session: DB) -> dict[str, Any]:
        return _project(project_or_404(session, project_id))

    @api.post("/projects/{project_id}/uploads", status_code=201)
    async def upload(project_id: int, request: Request, session: DB, file: UploadFile,
                     role: Annotated[str, Form()],
                     for_upload: Annotated[int | None, Form()] = None,
                     ) -> dict[str, Any]:  # fmt: skip
        project_or_404(session, project_id)
        if role not in ROLES:
            raise HTTPException(422, f"role must be one of {', '.join(ROLES)}")
        if (role == "mapping") != (for_upload is not None):
            raise HTTPException(422, "a mapping names the upload it describes (for_upload)")
        if for_upload is not None:
            target = session.get(Upload, for_upload)
            if target is None or target.project_id != project_id or target.role == "mapping":
                raise HTTPException(422, "for_upload must be a file of this project")
        limit = settings.max_upload_mb * 1024 * 1024
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"files are limited to {settings.max_upload_mb} MB")
        row = Upload(project_id=project_id, role=role, filename=_safe_name(file.filename),
                     sha256=storage.put(data), size=len(data),
                     for_upload_id=for_upload)  # fmt: skip
        session.add(row)
        session.flush()
        activity.log(session, who(request), "file uploaded", project_id, upload=row.id,
                     filename=row.filename, role=role)  # fmt: skip
        session.commit()
        return _upload(row)

    @api.get("/projects/{project_id}/uploads")
    def list_uploads(project_id: int, session: DB) -> list[dict[str, Any]]:
        project_or_404(session, project_id)
        rows = session.query(Upload).filter(Upload.project_id == project_id).order_by(Upload.id)
        return [_upload(u) for u in rows]

    @api.post("/projects/{project_id}/runs", status_code=202)
    def start_run(project_id: int, body: RunIn, request: Request, session: DB,
                  background: BackgroundTasks) -> dict[str, Any]:  # fmt: skip
        project_or_404(session, project_id)
        pack = _packs(settings.packs_dir).get(body.pack)
        if pack is None:
            raise HTTPException(422, f"no pack named {body.pack!r}")
        uploads = session.query(Upload).filter(Upload.id.in_(body.uploads)).all()
        foreign = any(u.project_id != project_id for u in uploads)
        if len(uploads) != len(set(body.uploads)) or foreign:
            raise HTTPException(422, "uploads must be files of this project")
        if not any(u.role == "architect" for u in uploads):
            raise HTTPException(422, "a run needs at least one architect file")
        uploads.sort(key=lambda u: u.id)
        run = Run(project_id=project_id, pack_name=pack.name, pack_version=pack.version,
                  pack_hash=pack.content_hash, upload_ids=[u.id for u in uploads],
                  upload_hashes=[u.sha256 for u in uploads])  # fmt: skip
        session.add(run)
        session.flush()
        activity.log(session, who(request), "check run", project_id, run=run.id,
                     pack=f"{pack.name} {pack.version}")  # fmt: skip
        session.commit()
        background.add_task(jobs.execute, run.id, sessions, storage, pack)
        return _run(run)

    @api.get("/projects/{project_id}/runs")
    def list_runs(project_id: int, session: DB) -> list[dict[str, Any]]:
        project_or_404(session, project_id)
        return [_run(r) for r in session.query(Run).filter(Run.project_id == project_id)
                .order_by(Run.id)]  # fmt: skip

    @api.get("/projects/{project_id}/stats")
    def project_stats(project_id: int, session: DB) -> dict[str, Any]:
        """Per run and in total: findings raised, accepted, dismissed, not yet reviewed."""
        project_or_404(session, project_id)
        runs = session.query(Run).filter(Run.project_id == project_id).order_by(Run.id).all()
        per_run = []
        for run in runs:
            raised = (session.query(FindingRow).filter(FindingRow.run_id == run.id,
                      FindingRow.status.in_(("fail", "not_checked"))).all())  # fmt: skip
            counts = {"raised": len(raised), "accepted": 0, "dismissed": 0, "unreviewed": 0}
            for row in raised:
                latest = row.reviews[-1].decision if row.reviews else None
                key = {"accept": "accepted", "dismiss": "dismissed"}.get(latest, "unreviewed")
                counts[key] += 1
            per_run.append({"run": run.id, "created": iso(run.created), **counts})
        total = {k: sum(r[k] for r in per_run)
                 for k in ("raised", "accepted", "dismissed", "unreviewed")}  # fmt: skip
        return {"project": project_id, "total": total, "runs": per_run}

    @api.get("/runs/{run_id}")
    def get_run(run_id: int, session: DB) -> dict[str, Any]:
        return _run(run_or_404(session, run_id))

    @api.get("/runs/{run_id}/findings")
    def findings(run_id: int, session: DB, status: str | None = None) -> list[dict[str, Any]]:
        run_or_404(session, run_id)
        rows = session.query(FindingRow).filter(FindingRow.run_id == run_id)
        if status:
            rows = rows.filter(FindingRow.status.in_(status.split(",")))
        return [_finding(r) for r in rows.order_by(FindingRow.position)]

    @api.get("/runs/{run_id}/findings.csv")
    def findings_csv(run_id: int, session: DB) -> Response:
        run_or_404(session, run_id)
        open_items = FindingRow.status.in_(("fail", "not_checked"))
        rows = (session.query(FindingRow).filter(FindingRow.run_id == run_id, open_items)
                .order_by(FindingRow.position))  # fmt: skip
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            f = _finding(row)
            review = f["review"] or {}
            sources = "; ".join(describe_source(SourceRef.from_dict(s)) for s in f["evidence"])
            cells = [f["id"], f["severity"], f["status"], f["mark"], f["rule_id"], f["message"],
                     f["expected"], f["reason"], review.get("decision"), review.get("reason"),
                     sources]  # fmt: skip
            # Customer text must not turn into a spreadsheet formula when the file is opened.
            writer.writerow(["'" + c if isinstance(c, str) and c[:1] in "=+-@" else c
                             for c in cells])  # fmt: skip
        disposition = f'attachment; filename="run-{run_id}-findings.csv"'
        return Response(out.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": disposition})  # fmt: skip

    @api.get("/findings/{finding_id}")
    def finding(finding_id: int, session: DB) -> dict[str, Any]:
        row = session.get(FindingRow, finding_id)
        if row is None:
            raise HTTPException(404, "no such finding")
        return {**_finding(row), "reviews": [_review(r) for r in row.reviews],
                "files": row.run.files or {}}  # fmt: skip

    @api.post("/findings/{finding_id}/review", status_code=201)
    def review(finding_id: int, body: ReviewIn, request: Request, session: DB) -> dict[str, Any]:
        row = session.get(FindingRow, finding_id)
        if row is None:
            raise HTTPException(404, "no such finding")
        if body.decision == "dismiss" and not body.reason.strip():
            raise HTTPException(422, "a dismissal needs a reason")
        decision = Review(finding_id=row.id, decision=body.decision, reason=body.reason.strip(),
                          user_name=who(request))  # fmt: skip
        session.add(decision)
        activity.log(session, who(request), f"finding {body.decision}ed", row.run.project_id,
                     finding=row.id, rule=row.rule_id, mark=row.mark)  # fmt: skip
        session.commit()
        return _review(decision)

    TABLES = (".xlsx", ".xlsm", ".csv")

    def table_or_422(session: Session, upload_id: int) -> Upload:
        upload = session.get(Upload, upload_id)
        if upload is None or upload.role == "mapping":
            raise HTTPException(404, "no such file")
        if not upload.filename.lower().endswith(TABLES):
            raise HTTPException(422, "only .xlsx and .csv tables get a mapping here; PDF "
                                "schedules need a mapping file (mappings/examples)")  # fmt: skip
        return upload

    @contextmanager
    def named_copy(upload: Upload) -> Iterator[Path]:
        # The readers choose CSV or Excel by the file name; stored objects have none.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / upload.filename
            path.symlink_to(storage.object(upload.sha256))
            yield path

    def previous_mappings(session: Session, upload: Upload, headers: list[str]) -> list[dict]:
        """Saved mappings for the same kind of file whose columns are all in these headers."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        rows = (session.query(Upload).filter(Upload.role == "mapping")
                .order_by(Upload.id.desc()).limit(500))  # fmt: skip
        for m in rows:
            target = session.get(Upload, m.for_upload_id) if m.for_upload_id else None
            if m.sha256 in seen or target is None or target.role != upload.role:
                continue
            seen.add(m.sha256)
            try:
                mapping = yaml.safe_load(storage.object(m.sha256).read_text()) or {}
                schedule.load_mapping_dict(mapping)
            except (OSError, ValueError, yaml.YAMLError, TypeError, AttributeError):
                continue
            if table_columns.fits(mapping, headers):
                out.append({"upload": m.id, "filename": m.filename,
                            "project": target.project_id, "mapping": mapping})  # fmt: skip
            if len(out) == 5:
                break
        return out

    @api.get("/uploads/{upload_id}/columns")
    def upload_columns(upload_id: int, session: DB, header_row: int | None = None,
                       sheet: str | None = None) -> dict[str, Any]:  # fmt: skip
        upload = table_or_422(session, upload_id)
        side = Side.ERP if upload.role == "erp" else Side.ARCHITECT
        with named_copy(upload) as path:
            try:
                names = table_columns.sheets(path)
                rows = table_columns.read_rows(path, sheet)
            except Exception as exc:  # noqa: BLE001 - shown to the user, never a crash
                raise HTTPException(422, f"cannot read {upload.filename}: {exc}") from None
        out = table_columns.propose(rows, side, header_row)
        if sheet:
            out["mapping"]["sheet"] = sheet
        out["sheets"] = names
        out["previous"] = previous_mappings(session, upload, out["headers"])
        return out

    @api.post("/uploads/{upload_id}/mapping")
    def upload_mapping(upload_id: int, body: MappingIn, request: Request,
                       session: DB) -> dict[str, Any]:  # fmt: skip
        upload = table_or_422(session, upload_id)
        name = f"{Path(upload.filename).stem}.mapping.yaml"
        try:
            text = table_columns.to_yaml(body.mapping, name)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise HTTPException(422, f"mapping: {exc}") from None
        side = Side.ERP if upload.role == "erp" else Side.ARCHITECT
        with named_copy(upload) as path:
            elements, warnings = schedule.parse(path, body.mapping, side=side)
        out: dict[str, Any] = {
            "elements": len(elements),
            "quantity": sum(e.quantity for e in elements),
            "warnings": [w.message for w in warnings[:20]],
            "more_warnings": max(0, len(warnings) - 20),
            "upload": None,
        }
        if body.save:
            data = text.encode()
            row = Upload(project_id=upload.project_id, role="mapping", filename=name,
                         sha256=storage.put(data), size=len(data),
                         for_upload_id=upload.id)  # fmt: skip
            session.add(row)
            session.flush()
            activity.log(session, who(request), "columns set", upload.project_id,
                         upload=upload.id, filename=upload.filename)  # fmt: skip
            session.commit()
            out["upload"] = _upload(row)
        return out

    @api.get("/uploads/{upload_id}/pages/{page}.png")
    def page_image(upload_id: int, page: int, session: DB) -> Response:
        upload = session.get(Upload, upload_id)
        if upload is None or not upload.filename.lower().endswith(".pdf"):
            raise HTTPException(404, "no such PDF")
        png = render_page(storage.object(upload.sha256), page)
        if png is None:
            raise HTTPException(404, "no such page")
        return Response(png, media_type="image/png", headers={"X-Points-Scale": str(PAGE_SCALE)})

    @api.get("/runs/{run_id}/reports/{name}")
    def report(run_id: int, name: str, session: DB) -> FileResponse:
        run_or_404(session, run_id)
        folder = storage.run_dir(run_id)
        path = folder / Path(name).name
        is_report = name in REPORTS or (name.endswith(".marked.pdf") and "/" not in name)
        if not is_report or not path.is_file():
            raise HTTPException(404, "no such report")
        media = REPORTS.get(name, "application/pdf")
        return FileResponse(path, media_type=media, filename=path.name)

    @api.delete("/projects/{project_id}")
    def delete_project(project_id: int, request: Request, session: DB) -> dict[str, Any]:
        project = project_or_404(session, project_id)
        counts = data.delete_project(session, storage, project)
        activity.log(session, who(request), "project deleted", None, project=project_id,
                     **counts)  # fmt: skip
        session.commit()
        return {"deleted": project_id, **counts}

    @api.get("/projects/{project_id}/export")
    def export_project(project_id: int, request: Request, session: DB,
                       background: BackgroundTasks) -> FileResponse:  # fmt: skip
        project = project_or_404(session, project_id)
        path = data.export_project(session, storage, project)
        activity.log(session, who(request), "project exported", project_id)
        session.commit()
        background.add_task(path.unlink, missing_ok=True)
        name = f"ludwig-project-{project_id}.zip"
        return FileResponse(path, media_type="application/zip", filename=name)

    @api.get("/activity")
    def get_activity(session: DB, project_id: int | None = None,
                     limit: int = 200) -> list[dict[str, Any]]:  # fmt: skip
        return activity.recent(session, project_id, limit)

    @api.get("/status", dependencies=[Depends(require_admin)])
    def instance_status(session: DB) -> dict[str, Any]:
        from ludwig.api.db import User

        packs = [{"name": p.name, "version": p.version}
                 for p in _packs(settings.packs_dir).values()]  # fmt: skip
        counts = {"users": session.query(User).filter(User.active).count(),
                  "projects": session.query(Project).count()}  # fmt: skip
        return status.report(settings.version, packs, settings.storage_dir, settings.backup_dir,
                             settings.retention_days, counts)  # fmt: skip

    @api.get("/settings")
    def public_settings() -> dict[str, Any]:
        return {"retention_days": settings.retention_days}

    if settings.retention_days:
        days = settings.retention_days

        def retention_loop() -> None:
            while True:
                with sessions() as session:
                    data.purge_expired(session, storage, days)
                if app.state.stop.wait(6 * 3600):
                    return

        app.state.stop = threading.Event()
        threading.Thread(target=retention_loop, name="retention", daemon=True).start()

    app.include_router(auth_routes)
    app.include_router(user_routes)
    app.include_router(api)
    web = settings.web_dir
    if web is not None and (web / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app
