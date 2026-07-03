# Ludwig web UI — the first real UI ↔ engine wiring

A thin local web frontend onto the **real** compiler. Type a prompt → the genuine loop
(`agent.loop.run`: generate → execute → critic → repair) compiles it → you see the real critic
verdicts, the real OCCT HLR drawing, and download the real STEP/IFC. The prototype's faked
timer-loop is replaced by `webapp.service.compile_to_result`.

```bash
python3 cli.py --serve            # http://localhost:8765
python3 cli.py --serve 9000       # custom port
python3 webapp/server.py 8765     # direct
```

Needs the OCCT kernel (cadquery/ifcopenshell) and a `claude`-like CLI on PATH for live codegen —
i.e. run it through the project venv (`./run.sh` knows the venv; or `.venv/bin/python cli.py --serve`).

## What this is / isn't
- **Is:** the real engine behind a real UI. `studio.html` is the **Studio** — the art-directed
  viewfinder (Stage · Intent Bar · Activity Rail · Point-to-Navigate · Ambient Correctness) wired to
  the genuine loop and backends. The art direction is now applied to the live app itself; the old
  disconnected `prototype/` mock has been retired (see `docs/DESIGN_BRIEF_STUDIO_V2.md`).
- Stdlib only, zero new dependencies; the server is just another *frontend* onto the loop, like the
  CLI ([H4] — the loop is the truth, frontends/backends are swappable).

## Files
| File | What |
|---|---|
| `service.py`  | the real compile/edit/build/section paths, returned as JSON-safe data (`docs/CONTRACT.md`) |
| `server.py`   | stdlib `ThreadingHTTPServer`: serves the Studio + the `/api/*` contract + `/out/<artifact>` |
| `studio.html` | **the Studio** (v2) — full-bleed Stage, floating glass panels, ⌘K intent bar; offline, no CDN |
| `index.html`  | the classic single-prompt compiler page (`/index.html`), kept until the intent bar absorbs fresh compile |
