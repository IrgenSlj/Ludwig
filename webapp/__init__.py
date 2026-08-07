"""webapp — the local daemon: the JSON+SSE contract, the Studio, and the payload assembler.

- `server.py`  — the stdlib HTTP+SSE daemon (`/api/*`, health/shutdown/token, the cross-origin gate).
- `service.py` — the JSON payloads every transport shares (`docs/CONTRACT.md`); the one write path
                 (`build_from_ops`) both `/api/build` and the MCP `ludwig_build` tool pass through.
- `gallery.py` / `safety.py` — the trusted seeds and the public-demo envelope (`LUDWIG_DEMO=1`).
- `studio.html` — the Studio (v2) viewfinder.

Nothing is re-exported here on purpose: importing this package must not drag in the daemon, and
`service` pulls the geometry kernel. Import the module you need (`from webapp import service`).

This file exists so `webapp` is a real package like every other top-level package in the repo, rather
than an implicit namespace one — the difference only bites once Ludwig is installed as a wheel (the
D-series desktop app), where a namespace package can be merged with any other distribution that ships
a `webapp/`.
"""
