"""Ludwig daemon — FastAPI app (M0).

One endpoint that runs the *existing* loop (``ludwig.run``) and persists the result,
plus read endpoints for projects and artifact files. The loop is blocking and spawns
its own thread pool, so it runs in a worker thread to keep the event loop free.

Run it:
    ./.venv/bin/uvicorn daemon.app:app --reload --port 8765
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

# Import the existing orchestrator unchanged (strangler-fig).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ludwig  # noqa: E402

from . import db, store  # noqa: E402

app = FastAPI(title="Ludwig daemon", version="0.0-m0")

_EXT = {"code": ".py", "render": ".png", "hero": ".png", "preview": ".glb"}


class GenerateRequest(BaseModel):
    brief: str = Field(min_length=1)
    candidates: int = 3
    rounds: int = 3
    target: float = 8.0
    workers: int = 3
    quick: bool = False


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-") or "scene"


@app.get("/api/health")
def health() -> dict:
    blender = getattr(ludwig, "BLENDER", None)
    return {
        "status": "ok",
        "version": app.version,
        "blender": blender,
        "blender_found": bool(blender and os.path.exists(blender)),
        "provider": ludwig._provider_name() if hasattr(ludwig, "_provider_name") else None,
    }


@app.post("/api/generate")
async def generate(req: GenerateRequest) -> dict:
    candidates = 1 if req.quick else req.candidates
    rounds = 1 if req.quick else req.rounds
    mode = "agentic" if getattr(ludwig, "AGENTIC", False) else "oneshot"

    project_id = db.create_project(_slug(req.brief), req.brief)
    run_id = db.create_run(
        project_id,
        mode,
        {"candidates": candidates, "rounds": rounds, "target": req.target,
         "workers": req.workers, "quick": req.quick},
    )

    try:
        best = await run_in_threadpool(
            ludwig.run, req.brief,
            candidates=candidates, rounds=rounds,
            target=req.target, workers=req.workers,
        )
    except Exception as exc:  # noqa: BLE001 — surface any loop failure as a 500
        db.finish_run(run_id, status="error", error=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not best:
        db.finish_run(run_id, status="error", error="loop returned no candidate")
        raise HTTPException(status_code=500, detail="loop returned no candidate")

    artifacts: dict[str, str] = {}
    # the program (source of truth) — write it into the project folder
    if best.get("code"):
        p = store.write_text(project_id, "scene.py", best["code"])
        artifacts["code"] = db.add_artifact(run_id, "code", p)
    # the rendered outputs — copy from renders/ into the project folder
    for kind, key in (("render", "png"), ("hero", "hero")):
        src = best.get(key)
        if src:
            dest = store.copy_in(project_id, src, f"{kind}{_EXT[kind]}")
            if dest:
                artifacts[kind] = db.add_artifact(run_id, kind, dest)

    db.finish_run(run_id, status="done", score=best.get("score"),
                  critique=best.get("critique"))

    return {
        "project_id": project_id,
        "run_id": run_id,
        "score": best.get("score"),
        "critique": best.get("critique"),
        "artifacts": artifacts,
    }


@app.get("/api/projects")
def projects() -> dict:
    return {"projects": db.list_projects()}


@app.get("/api/projects/{project_id}")
def project(project_id: str) -> dict:
    p = db.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    return p


@app.get("/api/artifacts/{artifact_id}/file")
def artifact_file(artifact_id: str) -> FileResponse:
    a = db.get_artifact(artifact_id)
    if not a or not os.path.exists(a["path"]):
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(a["path"])
