"""The local daemon that serves the Studio and the JSON+SSE contract (docs/CONTRACT.md).

It serves `studio.html` — the **Studio (v2)**: the art-directed viewfinder (full-bleed Stage,
floating glass panels, ⌘K intent bar) wired to the *real* loop, so you see the *real* critic
verdicts, the *real* HLR/section drawings, and download the *real* STEP/IFC. The art direction now
lives in the live app; the old disconnected `prototype/` mock has been retired
(docs/DESIGN_BRIEF_STUDIO_V2.md). `index.html` remains at `/index.html` as the classic prompt page.

Local-first, BYO inference (it shells out to whatever `claude`-like CLI is on PATH via the existing
inference seam). Stdlib only — no web framework — so it adds zero dependencies to the core.

    python3 cli.py --serve            # then open http://localhost:8765
    python3 webapp/server.py 8765
"""
from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "out"


def token_ok(configured: str | None, provided: str | None) -> bool:
    """The loopback-auth rule (D1). No token configured → open (local dev + the public demo, which
    set none — back-compat). A token configured → require an exact, constant-time match. This is the
    whole security boundary the embedding shell relies on; keep it a pure function so --selftest can
    exercise it without a socket."""
    if not configured:
        return True
    return bool(provided) and hmac.compare_digest(str(provided), str(configured))

# DEMO mode (env LUDWIG_DEMO=1) is the safe public face. The browser may NOT submit a fresh program to
# exec (that is RCE — see webapp/safety.py): it picks trusted seeds by id and only NUMERIC parameter
# edits are accepted, and generation (compile/explore, which needs inference) is disabled. Off by
# default, so local `cli.py --serve` keeps full developer behavior.
DEMO = os.environ.get("LUDWIG_DEMO", "") not in ("", "0", "false", "False")

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

    def _authed(self) -> bool:
        """True if this request may touch the protected surface. The token (set by the embedding shell)
        arrives as an `X-Ludwig-Token` header OR a `?token=` query param; a daemon with no token stays
        open (D1)."""
        from urllib.parse import parse_qs, urlparse
        tok = getattr(self.server, "ludwig_token", None)   # per-server, not module-global (two daemons coexist)
        got = self.headers.get("X-Ludwig-Token") or parse_qs(urlparse(self.path).query).get("token", [""])[0]
        return token_ok(tok, got)

    def _unauthorized(self) -> None:
        from webapp import service
        self._send(401, json.dumps(service.stamp({"error": "unauthorized"})).encode(), "application/json")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/health":   # token-FREE readiness probe — the embedding shell polls it at boot
            from webapp import service
            self._send(200, json.dumps(service.stamp(
                {"ok": True, "name": "ludwig", "demo": DEMO, "tools": {}})).encode(), "application/json")
            return
        # Static UI is open (so the page can load); the API + fabrication artifacts are the guarded
        # surface — a local daemon that writes fab files must not answer every process on the machine.
        if (path.startswith("/api/") or path.startswith("/out/")) and not self._authed():
            self._unauthorized()
            return
        if path in ("/", "/studio", "/studio.html"):   # the Studio (v2) is the single front door
            self._send(200, (ROOT / "studio.html").read_bytes(), "text/html")
            return
        if path in ("/index.html", "/compile"):   # the classic prompt-compiler page (kept until the
            self._send(200, (ROOT / "index.html").read_bytes(), "text/html")   # Studio intent bar absorbs fresh compile
            return
        if path == "/api/gallery":   # trusted seed listing (id/title/blurb) + demo flag; no programs leave
            from webapp import gallery, service
            self._send(200, json.dumps(service.stamp({"demo": DEMO, "seeds": gallery.listing()})).encode(),
                       "application/json")
            return
        if path == "/api/compile_stream":   # live Activity Rail (Server-Sent Events)
            self._compile_stream()
            return
        if path == "/api/agent_stream":      # streaming agent runtime (R23) — token-free by default
            self._agent_stream()
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

    def _sse_begin(self):
        """Write SSE response headers and return the emit closure. Call once at the top of a stream
        handler; use the returned function for every subsequent `data:` write."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()

        def emit(obj) -> None:
            try:
                self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
                self.wfile.flush()
            except Exception:
                pass

        return emit

    def _compile_stream(self) -> None:
        """Stream the compile as Server-Sent Events so the UI paints a live Activity Rail. The loop's
        on_event fires in THIS handler thread (ThreadingHTTPServer), so writing each event here is safe.
        Ends with a single `result` event carrying the full payload — identical to /api/compile."""
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        event = self._sse_begin()

        try:
            if DEMO:  # the SSE twin of POST /api/compile — same lock: generation needs inference and
                      # exec's model-authored code, never exposed on the public box (RCE + cost DoS).
                raise PermissionError("generation is disabled in the public demo. Bring your own AI "
                                      "key and run Ludwig locally; direct manipulation of the gallery "
                                      "parts (drag dimensions → STEP/IFC/DXF) is free here.")
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

    def _agent_stream(self) -> None:
        """Stream the agent runtime as SSE (R23). Token-free by default (the local grammar — zero LLM).
        Query: instruction=<text> + seed=<id> (or program=<validated derivative>). Yields op/applied/
        done events and a final `result` payload. In DEMO the instruction's numbers are envelope-bounded
        BEFORE any kernel work, mirroring the /api/preview guard."""
        import re
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        event = self._sse_begin()

        try:
            instruction = (q.get("instruction", [""])[0] or "").strip()
            if not instruction:
                raise ValueError("empty instruction")
            program = self._program({"seed": q.get("seed", [None])[0], "program": q.get("program", [None])[0]})
            if DEMO:  # bound every number in the instruction before it can reach OCCT tessellation
                from webapp import safety
                if not all(safety.value_in_envelope(float(n)) for n in re.findall(r"-?\d+(?:\.\d+)?", instruction)):
                    raise PermissionError("a value in that request is out of range for the demo.")
            from webapp.service import agent_stream
            # DEMO → the token-free local grammar; local/BYO-key → the LLM hybrid (grammar first, else infer)
            infer = None
            if not DEMO:
                from agent.runtime import hybrid_infer
                infer = hybrid_infer
            result = agent_stream(instruction, program, on_event=event, infer=infer)
            if DEMO:  # defence-in-depth: re-check the produced program before surfacing it
                from webapp import gallery, safety
                final_prog = result.get("program", program)
                if not safety.within_envelope(final_prog):
                    raise PermissionError("result program contains out-of-range dimensions.")
                if not safety.is_safe_derivative(final_prog, gallery.programs()):
                    raise PermissionError("result program is not a safe derivative of a gallery seed.")
            event({"event": "result", "result": result})
        except Exception as e:
            event({"event": "error", "fatal": f"{type(e).__name__}: {e}"})

    def _program(self, req: dict) -> str:
        """Resolve the program to operate on. A `seed` id loads the trusted server-side program; a
        client `program` is allowed verbatim in local mode, but in DEMO must be a numeric-only
        derivative of a gallery seed (webapp/safety.py) — anything else is rejected before it runs."""
        seed = req.get("seed")
        if seed:
            from webapp import gallery
            prog = gallery.program_for(seed)
            if prog is None:
                raise ValueError(f"unknown seed {seed!r}")
            return prog
        program = req.get("program") or ""
        if not program:
            raise ValueError("need a `seed` id or a `program`")
        if DEMO:
            from webapp import gallery, safety
            if not safety.is_safe_derivative(program, gallery.programs()):
                raise PermissionError("program rejected — the public demo only runs the gallery seeds "
                                      "with their dimensions changed (no arbitrary code).")
            if not safety.within_envelope(program):   # block giant/non-finite dims (tessellation DoS)
                raise PermissionError("dimensions out of range — keep edits within a sane physical size.")
        return program

    def _check_param_bounds(self, param: dict) -> None:
        """Bound a slider's old/new in DEMO — the substituted value reaches OCCT tessellation after the
        program-level within_envelope check ran, so an unbounded `new` would re-open the dimension DoS."""
        if not DEMO:
            return
        from webapp import safety
        for key in ("old", "new"):
            if not safety.value_in_envelope(param.get(key)):
                raise PermissionError("parameter value out of range — keep edits within a sane size.")

    def _out_dir(self, req: dict) -> Path:
        """The artifact directory for THIS request. Concurrent visitors on the shared public URL must not
        clobber each other's `out/<id>.step` (last-write-wins → you could download someone else's file), so
        each browser sends a random `session` and its artifacts land in out/<session>/. The token is
        sanitised to [a-z0-9] (no traversal); a missing/blank one falls back to the shared OUT (local use)."""
        raw = str(req.get("session") or "")
        safe = "".join(c for c in raw if c.isalnum())[:32]
        return (OUT / safe) if safe else OUT

    def do_POST(self) -> None:
        if not self._authed():   # every POST is a protected /api/* write — gate before reading a body
            self._unauthorized()
            return
        if self.path == "/api/shutdown":   # the embedding shell reaps the daemon on window close
            import threading
            from webapp import service
            self._send(200, json.dumps(service.stamp({"ok": True})).encode(), "application/json")
            # shutdown() must not run in this handler thread (it would deadlock serve_forever) — off-thread it
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path not in ("/api/compile", "/api/edit", "/api/explore", "/api/adopt",
                             "/api/preview", "/api/section", "/api/hole", "/api/plan", "/api/build"):
            self._send(404, b"not found", "text/plain")
            return
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            self._send(400, b"bad content-length", "text/plain")
            return
        if n > 262_144:   # 256 KB — a seed + numeric edits is tiny; refuse multi-GB body DoS
            self._send(413, b"request too large", "text/plain")
            return
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path in ("/api/compile", "/api/explore", "/api/plan", "/api/build"):
                if DEMO:  # generation/planning needs inference (and building runs a fresh plan) — off in demo
                    raise PermissionError("generation is disabled in the public demo. Bring your own AI "
                                          "key and run Ludwig locally; direct manipulation of the gallery "
                                          "parts (drag dimensions → STEP/IFC/DXF) is free here.")
                if self.path == "/api/plan":       # propose a reviewable op-plan (writes nothing)
                    from webapp.service import plan_to_result
                    result = plan_to_result((req.get("instruction") or "").strip(),
                                            program=req.get("program") or "")
                    self._send(200, json.dumps(result).encode(), "application/json")
                    return
                if self.path == "/api/build":      # build a client-reviewed plan (validated ops, never exec'd)
                    from webapp.service import build_from_ops
                    result = build_from_ops(req.get("program") or "", req.get("ops") or [],
                                            out=self._out_dir(req))
                    self._send(200, json.dumps(result).encode(), "application/json")
                    return
                prompt = (req.get("prompt") or "").strip()
                if not prompt:
                    raise ValueError("empty prompt")
                if self.path == "/api/compile":
                    from webapp.service import compile_to_result
                    result = compile_to_result(prompt, candidates=int(req.get("candidates", 1)),
                                               rounds=int(req.get("rounds", 2)))
                else:
                    from webapp.service import explore_to_result
                    result = explore_to_result(prompt, n=int(req.get("n") or 3))
            elif self.path == "/api/adopt":  # load a seed (or re-execute a chosen variant) — token-free
                from webapp.service import adopt_to_result
                result = adopt_to_result(self._program(req), out=self._out_dir(req))
            elif self.path == "/api/preview":  # live direct-manipulation: geometry-only, no files/backends
                program = self._program(req)
                param = req.get("param") or {}
                if not {"name", "old", "new"} <= set(param):
                    raise ValueError("preview needs param{name, old, new}")
                self._check_param_bounds(param)   # the substituted `new` reaches the kernel — bound it
                from webapp.service import preview_edit
                result = preview_edit(program, param["name"], float(param["old"]), float(param["new"]))
            elif self.path == "/api/section":  # live cut plane: geometry-only section mesh, no files/LLM
                program = self._program(req)
                axis = req.get("axis")
                if axis is not None and axis not in ("x", "y", "z"):
                    raise ValueError("section axis must be x, y or z")
                offset = req.get("offset")
                if offset is not None:
                    offset = float(offset)
                    from webapp import safety
                    if DEMO and not safety.value_in_envelope(offset):   # the plane pos reaches the kernel
                        raise PermissionError("section offset out of range — keep it within a sane size.")
                from webapp.service import section_to_result
                result = section_to_result(program, axis=axis, offset=offset)
            elif self.path == "/api/hole":     # drag a hole in plan: re-bore live, deterministic + token-free
                program = self._program(req)
                frm, to = req.get("from"), req.get("to")
                if not (isinstance(frm, list) and isinstance(to, list) and len(frm) == 2 and len(to) == 2):
                    raise ValueError("hole move needs from[x,y] and to[x,y]")
                to = [float(to[0]), float(to[1])]
                if DEMO:                        # the new centre reaches the kernel — bound both coords
                    from webapp import safety
                    if not all(safety.value_in_envelope(v) for v in to):
                        raise PermissionError("hole position out of range — keep it within a sane size.")
                if req.get("commit"):
                    from webapp.service import hole_move_to_result
                    result = hole_move_to_result(program, [float(frm[0]), float(frm[1])], to)
                else:
                    from webapp.service import preview_hole_move
                    result = preview_hole_move(program, [float(frm[0]), float(frm[1])], to)
            else:  # /api/edit — re-prompt an existing program into a minimal diff (S6)
                program = self._program(req)
                param = req.get("param")
                instruction = (req.get("instruction") or "").strip()
                if DEMO and not (param and {"name", "old", "new"} <= set(param)):
                    raise PermissionError("the public demo only commits numeric parameter edits (drag a "
                                          "dimension). Free-text agent edits need your own AI key locally.")
                if param:
                    self._check_param_bounds(param)   # the substituted `new` reaches the kernel — bound it
                if not instruction:
                    raise ValueError("edit needs an `instruction`")
                from webapp.service import edit_to_result
                result = edit_to_result(program, instruction, param=param,
                                        rounds=min(int(req.get("rounds", 1)), 5),  # cap the repair-loop amplifier
                                        allow_llm=not DEMO,   # demo: never exec model-authored code
                                        out=self._out_dir(req))
            self._send(200, json.dumps(result).encode(), "application/json")
        except Exception as e:  # never 500 silently — the UI shows the reason
            from webapp import service
            self._send(200, json.dumps(service.stamp({"fatal": f"{type(e).__name__}: {e}"})).encode(),
                       "application/json")

    def log_message(self, *_args) -> None:  # quiet by default
        pass


def make_server(port: int = 8765, *, token: str | None = None) -> ThreadingHTTPServer:
    """Build (but don't run) the daemon. `port=0` binds an OS-assigned ephemeral port — read it back
    from `.server_address[1]`. The token is stored on the server instance (not a module global) so two
    daemons can coexist on one machine with distinct tokens. Split from serve() so tests can drive it."""
    OUT.mkdir(exist_ok=True)
    host = os.environ.get("LUDWIG_HOST", "127.0.0.1")  # 0.0.0.0 in a container (set in the Dockerfile)
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.ludwig_token = token
    return httpd


def serve(port: int = 8765, *, token: str | None = None) -> int:
    httpd = make_server(port, token=token)
    host = httpd.server_address[0]
    chosen = httpd.server_address[1]                   # the actual port (== port, or the ephemeral one)
    print(f"Ludwig daemon on http://{host}:{chosen}  (Ctrl-C to stop)")
    print(f"PORT={chosen}", flush=True)                # machine-readable line for the embedding shell
    if token:
        print("token auth: on (send X-Ludwig-Token header or ?token=)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    import sys
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
