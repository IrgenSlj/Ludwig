"""Recorder — the thing that actually WRITES a run to the `RunStore` (WS7).

`telemetry/store.py` has shipped the on-disk layout since M1, and until now nothing called it: the
`runs/` directory held only `.gitkeep`, and every live run — including expensive eval and bench runs —
finished without leaving a trace. WS7's whole value is the trajectory dataset; a store nobody writes
to accumulates nothing.

**It attaches through the loop's existing `on_event` seam and changes no loop code** — the same
[H4] property the critic panel and the backend registry have. `agent.loop.run` already emits a
stage/status event at every step for the Studio's Activity Rail; a recorder is just another
subscriber, and `fanout()` lets the Studio and the store both listen.

Two rules this module holds to:

- **Telemetry never breaks a run.** Every disk touch is wrapped: a full disk, a read-only mount or a
  bad `runs_dir` degrades to "no telemetry", never to a failed compile. A recording tool that can
  take down the thing it records is worse than no recording.
- **Provenance over volume.** The manifest pins what would otherwise be unreproducible — resolved
  config hash, the models actually used, the git commit, the brief — because a trajectory you can't
  attribute to a code state isn't a dataset, it's a log.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable, Optional

from telemetry.store import RunStore


def enabled(cfg=None) -> bool:
    """Is telemetry on? `LUDWIG_TELEMETRY=off` wins (so one run can opt out without editing config),
    else `ludwig.toml: telemetry.enabled`. Never raises — a broken config means telemetry off, which
    is the safe direction."""
    env = os.environ.get("LUDWIG_TELEMETRY")
    if env is not None:
        return env.strip().lower() in ("1", "on", "true", "yes")
    try:
        if cfg is None:
            from agent.config import load_config
            cfg = load_config()
        return bool(cfg.telemetry.enabled)
    except Exception:
        return False


def new_run_id(prefix: str = "run") -> str:
    """A sortable, collision-free run id: `<prefix>_<utc-stamp>_<short-uuid>`. Sortable matters —
    `ls runs/` should read chronologically without parsing a manifest."""
    return f"{prefix}_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{uuid.uuid4().hex[:6]}"


def git_commit() -> Optional[str]:
    """The current commit, or None outside a repo. Reads `.git` directly rather than shelling out to
    `git` — no subprocess in the telemetry path, and it works when git isn't installed."""
    try:
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / ".git"
        head = (root / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = root / head[5:]
            if ref.exists():
                return ref.read_text(encoding="utf-8").strip()[:40]
            for line in (root / "packed-refs").read_text(encoding="utf-8").splitlines():
                if line.endswith(head[5:]):
                    return line.split()[0][:40]
            return None
        return head[:40] or None
    except Exception:
        return None


def fanout(*callbacks) -> Callable[[dict], None]:
    """Compose several `on_event` subscribers into one. This is what lets the Studio's Activity Rail
    and the trajectory store observe the same run without either knowing about the other."""
    subs = [c for c in callbacks if c]

    def _emit(ev: dict) -> None:
        for c in subs:
            try:
                c(ev)
            except Exception:
                pass
    return _emit


class Recorder:
    """Writes one run's manifest + trajectory. Use as a context manager, or call `finish()` yourself.

    `Recorder(enabled=False)` is a fully working no-op, so callers never branch on whether telemetry
    is on — they wire it in unconditionally and the flag decides whether bytes land.
    """

    def __init__(self, kind: str, *, cfg=None, runs_dir: Optional[str] = None,
                 run_id: Optional[str] = None, on: Optional[bool] = None) -> None:
        self.kind = kind
        self.cfg = cfg
        self.enabled = enabled(cfg) if on is None else bool(on)
        self.run_id = run_id or new_run_id(kind)
        self.started = time.time()
        self.events = 0
        self.store: Optional[RunStore] = None
        if not self.enabled:
            return
        try:
            if runs_dir is None:
                runs_dir = getattr(getattr(cfg, "telemetry", None), "runs_dir", None) or "runs"
            self.store = RunStore(self.run_id, runs_dir=runs_dir)
        except Exception:
            self.store = None
            self.enabled = False

    # -- manifest ---------------------------------------------------------- #
    def begin(self, **fields: Any) -> "Recorder":
        """Write the manifest. Everything here is provenance the trajectory alone can't reconstruct."""
        if self.store is None:
            return self
        manifest = {
            "kind": self.kind,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started)),
            "git_commit": git_commit(),
            "schema_version": _schema_version(),
            **fields,
        }
        if self.cfg is not None:
            try:
                manifest["config_hash"] = self.cfg.config_hash()
                manifest["config"] = self.cfg.as_dict()
            except Exception:
                pass
        try:
            self.store.write_manifest(manifest)
        except Exception:
            self.store = None
            self.enabled = False
        return self

    # -- trajectory -------------------------------------------------------- #
    def on_event(self, ev: dict) -> None:
        """The `on_event` subscriber. Stamps a monotonic sequence + wall offset onto each event, so a
        trajectory replays in true order even if two events share a timestamp."""
        if self.store is None:
            return
        try:
            self.events += 1
            self.store.append_event({"seq": self.events,
                                     "t": round(time.time() - self.started, 4), **ev})
        except Exception:
            self.store = None            # disk went away mid-run; stop trying, don't fail the run

    def finish(self, result=None, **fields: Any) -> Optional[str]:
        """Close the run: append a terminal event and fold the outcome into the manifest. Returns the
        run id when something was written, else None (so a caller can print where it landed)."""
        if self.store is None:
            return None
        outcome = dict(fields)
        if result is not None:
            outcome.update({
                "passed": bool(getattr(result, "passed", False)),
                "rounds": getattr(result, "rounds", None),
                "error": getattr(result, "err", None),
            })
        outcome["elapsed_s"] = round(time.time() - self.started, 3)
        self.on_event({"stage": "run", "status": "done", **outcome})
        try:
            manifest = self.store.read_manifest() or {}
            manifest.update({"outcome": outcome, "events": self.events})
            self.store.write_manifest(manifest)
        except Exception:
            return None
        return self.run_id

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            self.finish(error=f"{exc_type.__name__}: {exc}")
        elif self.store is not None:
            self.finish()
        return False                      # never swallow the caller's exception


def _schema_version() -> Optional[str]:
    """Pin the wire-contract version (A1) into the manifest so an exported trajectory says which
    payload shape it was recorded against."""
    try:
        from webapp.service import SCHEMA_VERSION
        return SCHEMA_VERSION
    except Exception:
        return None
