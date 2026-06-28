# Ludwig — desktop shell (Tauri)

The native desktop wrapper for the Ludwig **Stage & Director** UI (BRIEF §7 / P3). It is a thin,
honest shell: on launch the Rust side (`src-tauri/src/lib.rs`) spawns the real Python backend
(`python3 cli.py --serve 8765` from the repo root) and the window loads that webapp — so the desktop
app and `cli.py --serve` are the **same** UI on the **same** real compiler, never a fork.

> The full Stage & Director experience already runs in any browser via `python3 cli.py --serve` →
> http://localhost:8765. This shell only packages it as a double-click desktop app (the P3 "no CLI"
> gate). The UI is identical; building it is a distribution step, not a feature.

## Run / build

Requires Node + a Rust toolchain (`cargo`, `rustc`) and, on macOS, the Xcode command-line tools
(system WebKit provides the webview).

```bash
cd desktop
npm install            # if node_modules/ is absent
npm run dev            # launches the app in dev (spawns the Python backend + opens the window)
npm run build          # bundles a distributable .app / .dmg into src-tauri/target/release/bundle
```

The Python backend must be importable from the repo root — i.e. run from a checkout where
`cli.py` and the `.venv` (with `cadquery`, `ezdxf`, `ifcopenshell`) are present. The shell locates
the repo by walking up to the directory containing `cli.py`.

## What's here

- `frontend/index.html` — a tiny bootstrap page that polls `http://localhost:8765` and redirects once
  the backend is up (so the window shows a "Starting Ludwig…" splash, then the real Stage).
- `src-tauri/` — the Rust shell: `lib.rs` spawns + reaps the Python server; `tauri.conf.json` sets the
  window (1280×800) and bundle config.

`src-tauri/target/` (the native build tree, hundreds of MB) is gitignored — never commit it.
