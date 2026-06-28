"""A thin local web frontend onto the real compiler — the first wiring of UI ↔ engine.

This is NOT the art-directed Tauri shell (that is P3 / `prototype/`). It is the smallest honest
thing: a browser page where you type a prompt, the *real* loop compiles it, and you see the *real*
critic verdicts, the *real* HLR drawing, and download the *real* STEP/IFC. It replaces the
prototype's faked timer-loop with the genuine `webapp.service.compile_to_result`.

Local-first, BYO inference (it shells out to whatever `claude`-like CLI is on PATH via the existing
inference seam). Stdlib only — no web framework — so it adds zero dependencies to the core.

    python3 cli.py --serve            # then open http://localhost:8765
    python3 webapp/server.py 8765
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "out"

_TYPES = {".html": "text/html", ".svg": "image/svg+xml", ".step": "application/step",
          ".ifc": "application/x-step", ".py": "text/plain", ".js": "text/javascript",
          ".dxf": "image/vnd.dxf", ".png": "image/png"}
_INLINE = {".svg", ".png"}   # shown in-browser (drawing preview); other artifacts download


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str, *, download: str | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # dev server — always serve fresh UI/artifacts
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, (ROOT / "index.html").read_bytes(), "text/html")
            return
        if path == "/api/compile_stream":   # live Activity Rail (Server-Sent Events)
            self._compile_stream()
            return
        if path.startswith("/out/"):
            f = (OUT / path[len("/out/"):]).resolve()
            if OUT.resolve() in f.parents and f.exists():  # no path traversal outside out/
                ctype = _TYPES.get(f.suffix, "application/octet-stream")
                inline = f.suffix in _INLINE
                self._send(200, f.read_bytes(), ctype, download=None if inline else f.name)
                return
        if path.startswith("/vendor/"):  # vendored three.js — local, no CDN (offline + load-reliable)
            f = (ROOT / "vendor" / path[len("/vendor/"):]).resolve()
            vendor = (ROOT / "vendor").resolve()
            if (vendor == f or vendor in f.parents) and f.is_file():
                self._send(200, f.read_bytes(), _TYPES.get(f.suffix, "application/octet-stream"))
                return
        self._send(404, b"not found", "text/plain")

    def _compile_stream(self) -> None:
        """Stream the compile as Server-Sent Events so the UI paints a live Activity Rail. The loop's
        on_event fires in THIS handler thread (ThreadingHTTPServer), so writing each event here is safe.
        Ends with a single `result` event carrying the full payload — identical to /api/compile."""
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()

        def event(obj) -> None:
            try:
                self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
                self.wfile.flush()
            except Exception:
                pass

        try:
            prompt = (q.get("prompt", [""])[0] or "").strip()
            if not prompt:
                raise ValueError("empty prompt")
            from webapp.service import compile_to_result
            result = compile_to_result(
                prompt, candidates=int(q.get("candidates", ["1"])[0]),
                rounds=int(q.get("rounds", ["2"])[0]),
                on_event=lambda ev: event({"event": "stage", **ev}))
            event({"event": "result", "result": result})
        except Exception as e:
            event({"event": "error", "fatal": f"{type(e).__name__}: {e}"})

    def do_POST(self) -> None:
        if self.path not in ("/api/compile", "/api/edit"):
            self._send(404, b"not found", "text/plain")
            return
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/compile":
                prompt = (req.get("prompt") or "").strip()
                if not prompt:
                    raise ValueError("empty prompt")
                from webapp.service import compile_to_result
                result = compile_to_result(prompt, candidates=int(req.get("candidates", 1)),
                                           rounds=int(req.get("rounds", 2)))
            else:  # /api/edit — re-prompt an existing program into a minimal diff (S6)
                program = req.get("program") or ""
                instruction = (req.get("instruction") or "").strip()
                if not program or not instruction:
                    raise ValueError("edit needs both `program` and `instruction`")
                from webapp.service import edit_to_result
                result = edit_to_result(program, instruction, param=req.get("param"),
                                        rounds=int(req.get("rounds", 1)))
            self._send(200, json.dumps(result).encode(), "application/json")
        except Exception as e:  # never 500 silently — the UI shows the reason
            self._send(200, json.dumps({"fatal": f"{type(e).__name__}: {e}"}).encode(),
                       "application/json")

    def log_message(self, *_args) -> None:  # quiet by default
        pass


def serve(port: int = 8765) -> int:
    OUT.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Ludwig web UI on http://localhost:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    import sys
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
