"""RunStore — the on-disk layout for one run's telemetry (WS7 home; thin stdlib version).

Layout::

    runs/<run_id>/
        manifest.json          # config hash, model versions, seed, git commit, budgets
        trajectory.jsonl       # append-only typed events (WS1 schema; dicts here in M1)
        media/<sha256>.<ext>    # content-addressed renders/exports, referenced by hash

Dependency-light on purpose: stdlib `json`/`hashlib`/`pathlib` only. WS7 layers the pydantic event
schema and `replay`/`export` on top of this store, importing pydantic lazily so the spine stays green.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Optional

_MANIFEST = "manifest.json"
_TRAJECTORY = "trajectory.jsonl"
_MEDIA = "media"


class RunStore:
    """Read/write one run directory. Creating the store does not touch disk until a write happens."""

    def __init__(self, run_id: str, *, runs_dir: str | Path = "runs") -> None:
        self.run_id = run_id
        self.root = Path(runs_dir) / run_id

    # -- paths ------------------------------------------------------------- #
    @property
    def manifest_path(self) -> Path:
        return self.root / _MANIFEST

    @property
    def trajectory_path(self) -> Path:
        return self.root / _TRAJECTORY

    @property
    def media_dir(self) -> Path:
        return self.root / _MEDIA

    def _ensure(self) -> None:
        self.media_dir.mkdir(parents=True, exist_ok=True)

    # -- manifest ---------------------------------------------------------- #
    def write_manifest(self, manifest: dict[str, Any]) -> Path:
        """Write (overwrite) the run manifest. Records `run_id` alongside the caller's fields."""
        self._ensure()
        payload = {"run_id": self.run_id, **manifest}
        self.manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return self.manifest_path

    def read_manifest(self) -> Optional[dict[str, Any]]:
        if not self.manifest_path.exists():
            return None
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    # -- trajectory -------------------------------------------------------- #
    def append_event(self, event: dict[str, Any]) -> None:
        """Append one event as a JSON line. Order on disk is the run's true event order."""
        self._ensure()
        with self.trajectory_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    def extend_events(self, events: Iterable[dict[str, Any]]) -> None:
        for event in events:
            self.append_event(event)

    def read_events(self) -> list[dict[str, Any]]:
        """Read the trajectory back in write order. Blank lines are skipped defensively."""
        if not self.trajectory_path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self.trajectory_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    # -- media (content-addressed) ---------------------------------------- #
    def put_media(self, data: bytes, *, ext: str = "png") -> str:
        """Store `data` at `media/<sha256>.<ext>` and return the sha256 hex digest.

        Content-addressed: identical bytes de-duplicate to one file and are referenced by hash from
        trajectory events (WS7 schema), so a manifest+trajectory pair fully reconstructs a run's media.
        """
        self._ensure()
        digest = hashlib.sha256(data).hexdigest()
        ext = ext.lstrip(".")
        path = self.media_dir / f"{digest}.{ext}"
        if not path.exists():
            path.write_bytes(data)
        return digest

    def media_path(self, digest: str, *, ext: str = "png") -> Path:
        return self.media_dir / f"{digest}.{ext.lstrip('.')}"
