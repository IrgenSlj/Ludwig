"""SSE streaming of a generation run.

Runs the blocking ``ludwig.run`` loop in a worker thread, captures its stdout, turns
each line into a structured event (``progress.parse_line``), and yields them as
Server-Sent Events. A final ``done`` (or ``error``) event carries the persisted
project/run ids, score, critique and artifact ids.

``contextlib.redirect_stdout`` is process-global, so concurrent streaming runs are
serialized by ``_stream_lock`` — fine for a single-user local daemon.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import threading

import ludwig

from . import progress

_stream_lock = threading.Lock()
_FINAL = "__final__"


class _LineWriter(io.TextIOBase):
    """A stdout sink that splits into lines and forwards parsed events."""

    def __init__(self, emit):
        self._emit = emit
        self._buf = ""

    def write(self, s: str) -> int:  # type: ignore[override]
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            ev = progress.parse_line(line)
            if ev:
                self._emit(ev)
        return len(s)

    def flush(self) -> None:  # type: ignore[override]
        if self._buf.strip():
            ev = progress.parse_line(self._buf)
            if ev:
                self._emit(ev)
        self._buf = ""


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def run_and_stream(brief, *, candidates, rounds, target, workers,
                         project_id, run_id, persist):
    """Async generator of SSE frames for one generation run."""
    from . import db  # local import avoids a cycle at module load

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(ev):
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def worker():
        outcome = {"best": None, "error": None}
        writer = _LineWriter(emit)
        try:
            with _stream_lock, contextlib.redirect_stdout(writer):
                outcome["best"] = ludwig.run(
                    brief, candidates=candidates, rounds=rounds,
                    target=target, workers=workers,
                )
                writer.flush()
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = f"{type(exc).__name__}: {exc}"
        loop.call_soon_threadsafe(queue.put_nowait, (_FINAL, outcome))

    threading.Thread(target=worker, daemon=True).start()

    yield _sse({"type": "start", "project_id": project_id,
                "run_id": run_id, "brief": brief})

    while True:
        item = await queue.get()
        if isinstance(item, tuple) and item and item[0] == _FINAL:
            outcome = item[1]
            if outcome["error"]:
                db.finish_run(run_id, status="error", error=outcome["error"])
                yield _sse({"type": "error", "message": outcome["error"]})
            elif not outcome["best"]:
                db.finish_run(run_id, status="error", error="loop returned no candidate")
                yield _sse({"type": "error", "message": "loop returned no candidate"})
            else:
                best = outcome["best"]
                artifacts = persist(project_id, run_id, best)
                yield _sse({"type": "done", "project_id": project_id, "run_id": run_id,
                            "score": best.get("score"), "critique": best.get("critique"),
                            "artifacts": artifacts})
            break
        yield _sse(item)
