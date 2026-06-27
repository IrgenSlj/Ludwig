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
- **Is:** the smallest honest UI — one prompt, the real engine, real artifacts. Stdlib only, zero
  new dependencies; the server is just another *frontend* onto the loop, like the CLI ([H4] — the
  loop is the truth, frontends/backends are swappable).
- **Isn't:** the art-directed Stage & Director shell (that is P3 / `../prototype/`, a disconnected
  three.js mock). This is the vertical "hello world" that proves the wiring; the rich shell builds
  on top of this seam.

## Files
| File | What |
|---|---|
| `service.py` | `compile_to_result(prompt)` — the one real compile path, returned as JSON-safe data |
| `server.py`  | stdlib `ThreadingHTTPServer`: `GET /`, `POST /api/compile`, `GET /out/<artifact>` |
| `index.html` | self-contained UI (no CDN — works offline, unlike the prototype) |
