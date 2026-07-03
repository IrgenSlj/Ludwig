# Ludwig — macOS Desktop App Plan (the D-series)

*Companion to HARNESS_BRIEF.md. Turns the existing `desktop/` scaffold (Tauri v2 shell that spawns
`cli.py --serve` from a dev checkout) into a signed, notarized, double-clickable **Ludwig.app**
that a person with no Python, no terminal, and no checkout can install and use. One session = one
PR; the shell never forks the UI — the webapp stays the single Studio.*

> Principle: **the desktop app is a distribution step, not a feature** (desktop/README). Every
> capability lives in the daemon; the shell packages, launches, signs, and updates it.

---

## 0. The decision: how the Python engine ships inside a .app

Three options were weighed (research: Tauri v2 sidecar docs; community Tauri+Python packaging
patterns; PyInstaller child-process caveats):

| Option | How | Verdict |
|---|---|---|
| **A. PyInstaller onedir sidecar** (RECOMMENDED) | `pyinstaller` builds `ludwigd` as a **onedir** bundle (never onefile: onefile self-extracts on every launch and hides the real PID behind a bootloader — the known kill-the-child problem); the directory ships as a Tauri **resource**, with a tiny launcher registered as the `externalBin` sidecar | Offline-first, deterministic, signable. Cost: a large bundle (OCCT + IfcOpenShell + scipy ≈ 500–900 MB uncompressed; DMG compresses well). Heavy CAD apps are expected to be heavy. |
| B. First-launch bootstrap | Ship `uv` + a lockfile; create a venv in `~/Library/Application Support/Ludwig` on first run, downloading wheels (~300 MB) | Small installer, but first launch needs network, wheel availability per macOS/arch can drift, and notarization of downloaded code is a gray zone. Keep as documented fallback only. |
| C. Status quo (dev checkout) | Shell walks up to find `cli.py` + `.venv` | Fine for us; not a product. Retire once A ships. |

**LOCKED: Option A**, arm64 (Apple Silicon) first; Intel via a separate x86_64 build later only if
demand appears (2026 macOS installed base is overwhelmingly arm64).

**Bring-your-own stays bring-your-own:** the `claude`/`opencode` CLI and Blender are **not**
bundled. The app detects them on PATH (plus the standard install locations) and degrades honestly:
without an inference CLI, the token-free lanes (direct manipulation, sliders, sections, exports,
Op building from the deterministic grammar) all work; the Intent Bar shows a quiet "connect a
model" affordance linking to setup docs. This mirrors the product truth — Ludwig without a model
is still a verified CAD tool.

## 1. Architecture of the app

```
Ludwig.app/Contents/
  MacOS/ludwig            ← Tauri (Rust) shell binary
  Resources/
    ludwigd/              ← PyInstaller onedir: python runtime + engine + OCCT/IfcOpenShell/ezdxf/scipy
    webapp/               ← the Studio (same files the daemon serves; served BY the daemon)
  Info.plist              ← LSMinimumSystemVersion, identifier ai.ludwig.desktop
```
Runtime sequence: shell picks a **free ephemeral port** (not hardcoded 8765 — two instances, or a
user's own `--serve`, must not collide) → spawns `ludwigd --serve <port> --token <random>` →
splash polls `/api/health` → window navigates to `http://127.0.0.1:<port>?token=…`.

Hard rules:
- **Loopback only + session token.** The daemon binds 127.0.0.1 and requires the token the shell
  generated — a local daemon with fabrication-file write access must not be an open localhost API
  for every browser tab and process on the machine. (The token check is ~20 lines in `server.py`
  and benefits `cli.py --serve` users too; flag `--no-token` preserves the current behavior.)
- **Lifecycle:** shell owns the child; on window close it POSTs `/api/shutdown`, waits 2 s, then
  SIGTERMs the *process group* (onedir makes the PID honest, but group-kill anyway). A stale-port
  lockfile in Application Support prevents orphan daemons after a crash.
- **State lives in `~/Library/Application Support/Ludwig/`** (projects, store/*.sqlite, logs,
  packs cache) — never inside the .app (read-only, replaced on update). `standards.yaml` overrides
  resolve user-dir → project-dir → bundled default.

## 2. Signing, notarization, distribution (the part that always bites — plan it, don't discover it)

- **Apple Developer ID** (Irgen or a Ludwig entity, $99/yr). Sign **everything Mach-O inside the
  bundle** — the PyInstaller onedir contains dozens of .so/.dylib files (OCCT!), each needing
  `codesign --force --options runtime` with the Developer ID Application cert. This is scriptable
  (walk + sign, innermost-first) and MUST live in CI, not in hands.
- **Hardened runtime + entitlements:** `com.apple.security.cs.allow-unsigned-executable-memory`
  and `allow-dyld-environment-variables` are commonly required for Python/scientific stacks —
  start minimal, add only what crash logs prove necessary. No sandbox (App Store is a non-goal;
  we spawn processes and shell out to `claude`).
- **Notarization:** `notarytool submit` + staple, in CI. Budget one full session for the first
  green notarization — it is never green on the first try.
- **Distribution: DMG** (Tauri bundler) + a **Homebrew cask** (the developer audience's channel,
  and our first users are exactly that audience). GitHub Releases hosts both.
- **Updates:** Tauri's built-in updater (signed update manifests) checking GitHub Releases.
  In-app "a new version is available" — quiet, in the corner, per the design brief's calm rules.
  The daemon resource updates atomically with the shell (one bundle, one version — never split).

## 3. The D-series sessions (parallel to the A-series; no dependency on A1–A10 beyond a stable daemon)

**D1 — Daemon hardening for embedding.** `/api/health`, `/api/shutdown`, `--port 0` (ephemeral,
prints chosen port), `--token`; loopback bind asserted. *Gate:* selftest covers health/shutdown/
token-reject; two daemons coexist on one machine.

**D2 — PyInstaller onedir spec.** `ludwigd.spec` building the engine with cadquery + ifcopenshell +
ezdxf + scipy on macOS arm64, with the Studio's `webapp/` assets included as PyInstaller `datas`
(the daemon serves the UI from inside the onedir — one bundle, no loose files). **Pin the bundled
runtime to the newest PyInstaller-supported CPython (3.12/3.13 as of mid-2026), decoupled from the
3.14 dev env** — PyInstaller support lags the newest CPython, and CLAUDE.md's floor is 3.11+, so
the pin costs nothing; CI tests the engine on both the dev and the bundled version. A smoke script
runs the bracket compile → STEP inside the built dir. *Gate:* the onedir `ludwigd --selftest`
passes AND `--serve` serves the full Studio, on a machine with **no** Python installed.

**D3 — Shell integration.** Tauri spawns the bundled onedir (dev mode keeps the checkout path);
ephemeral port + token wiring; splash → Stage; process-group reap + stale-lock cleanup.
*Gate:* `npm run build` produces a .app that cold-launches to a working Stage on a clean macOS
account, offline, and leaves zero orphan processes after quit (verified via `pgrep`).

**D4 — External-tool detection.** PATH + known-location probes for `claude`/`opencode`/Blender at
daemon boot, surfaced in the result of `/api/health`; Studio shows the honest degraded state
(design brief §2). *Gate:* with no CLI present, every token-free lane works and the Intent Bar
shows the connect affordance; installing the CLI is picked up on next launch without reinstall.

**D5 — Sign + notarize in CI.** GitHub Actions (macos-14 arm64 runner): build onedir → deep-sign →
Tauri bundle → sign app → notarize → staple → DMG artifact. Secrets: cert + notary keys.
*Gate:* the CI DMG installs and launches on a stock Mac with Gatekeeper on, zero warnings.

**D6 — macOS chrome pass.** Menu bar (File/Edit/View/Window/Help mapped to daemon endpoints),
⌘K Intent Bar, ⌘1–⌘4 representations, native export dialogs + drag-out, OS theme auto-switch,
hiddenTitleBar traffic-light overlay, and **Help → Reveal Logs in Finder** (the daemon's log in
Application Support — the difference between a first user's bug report being useful or not).
(Implements design brief §2.) *Gate:* the keyboard-only
walkthrough: compile → inspect → section → export without touching the mouse.

**D7 — Updater + release v0.2.0.** Tauri updater against GitHub Releases; Homebrew cask PR;
`docs/INSTALL_MACOS.md`. *Gate:* v0.1.x app self-updates to v0.2.0; `brew install --cask ludwig`
works.

**D8 — [BUFFER] the notarization/entitlement debt session.** Reserved for the crash-log-driven
entitlement fixes, dylib stragglers, and first-user-report issues D2–D5 will generate. If unused,
it becomes the Intel-build decision session.

## 4. Risks
- **OCCT under PyInstaller** (missing dylibs, @rpath issues) — the classic. Mitigation: D2's gate
  is a *real compile* inside the built dir, not an import test; collect-all hooks for cadquery/OCP.
- **PyInstaller lagging the newest CPython** — solved structurally by D2's pin (bundled runtime ≠
  dev runtime); the pin is revisited, never silently bumped.
- **Bundle size sticker shock** — mitigation: DMG compression, honest release notes ("a full CAD
  kernel, offline"), and Homebrew where nobody reads sizes.
- **Notarization flakiness** — mitigation: D5 in CI from day one; D8 buffer.
- **Port/instance collisions & orphan daemons** — solved structurally in D1/D3 (ephemeral port,
  token, group-kill, lockfile); regression-tested in the gate.
- **Webview drift (WKWebKit vs Chrome)** — the Studio already runs in Safari-family engines via
  Tauri dev; add a WebKit smoke pass to D3's gate (three.js + SSE + EventSource are all safe, but
  verify, don't assume).

## 5. Non-goals
- Mac App Store (sandbox is incompatible with spawning BYO CLIs; revisit never, or when a
  sandboxed inference story exists).
- Bundling Blender or any inference runtime.
- Windows/Linux shells — the daemon + browser already serve them; shells follow demand, and the
  D-series artifacts (onedir spec, CI signing shape) transfer.
- Onefile builds, ever (self-extraction latency + PID dishonesty).
