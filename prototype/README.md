# Ludwig — Stage & Director prototype

The art-directed UI/UX prototype, imported from the Claude Design project
**"Ludwig: AI-Native Design Tool"** (`03ad9815-41f2-426e-b799-835915ff53e3`). It is the **P3
north-star** for the desktop app (the Tauri shell), made concrete and clickable now. See
[`../docs/UX_BRIEF.md`](../docs/UX_BRIEF.md) for the full art direction and the Code-side seams.

> **This is a self-contained mock, not wired to the compiler.** Geometry is three.js primitives and
> the compile/critic loop is faked with timers — exactly as a design prototype should be. The real
> wiring to the IR / backends / critic / agentic loop is **Phase 3**, gated behind P0–P2. It lives
> outside the Python package and the `--selftest` gate; it ships nothing into the core build.

## Run it

It needs to be served over HTTP (it uses an ES-module import for three.js and a relative
`./support.js`), so open it via a static server, not `file://`:

```bash
cd prototype
python3 -m http.server 8080
# then open http://localhost:8080/  (redirects to Ludwig.dc.html)
```

Requires internet on first load — `support.js` pulls React/ReactDOM/Babel and the page pulls
three.js, all from CDN.

## What to try (the signature interactions)

- **⌘K / Ctrl-K** — the Intent Bar. Pick a suggested intent → watch the Activity Rail stream the
  compile→derive→critic steps and the model rise onto the Stage.
- **Representation switcher** (bottom) — `3D · PLAN · SECTION · ELEV · RENDER`: one object reinterpreted
  (the section plane sweeps the solid; render develops the ground + light). Not separate files.
- **Click an element** on the Stage → Program Outline highlights its node + in-place parameter sliders
  appear + provenance ("Shaped by: …"). Geometry is the index into the program.
- **Grab a slider** → dependents light up (cascade preview) before the value changes.
- **Ambient correctness** — amber facade (below min thickness), red core/podium clash, teal verified
  room/anchors, painted onto the model, never a dialog.
- **Crystallization** (massing) — the loose, dashed roof vs `CRYSTALLIZE ROOF` snapping it to hard-line.
- **MASSING / PART** (top-right) — both beachheads, one interface, different depth.
- **Theme** — paper-light ⇄ graphite-dark.

## Files

| File | What |
|---|---|
| `Ludwig.dc.html` | the design source-of-record (Claude Design `.dc` format); the UI template + logic |
| `support.js` | the Claude Design runtime that renders `.dc` (self-bootstraps React/ReactDOM/Babel) |
| `index.html` | convenience redirect → `Ludwig.dc.html` |

To re-import an updated design later: pull the project's files again (DesignSync `get_file`) and
overwrite `Ludwig.dc.html` / `support.js`.
