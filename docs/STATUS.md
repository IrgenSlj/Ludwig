# Ludwig — status & plan of record (living)

*The one-page "where are we, what's next." The specs are [BRIEF.md](../BRIEF.md) (founding) +
[HARNESS_BRIEF.md](../HARNESS_BRIEF.md) (A-series) + [docs/MACOS_APP_PLAN.md](MACOS_APP_PLAN.md) (D-series) +
[docs/DESIGN_BRIEF_STUDIO_V2.md](DESIGN_BRIEF_STUDIO_V2.md) (Studio v2). This file tracks execution against
them. Update it as sessions land. Last updated 2026-07-04.*

## Tracked numbers ([H6])
- **First-pass geometric pass-rate** (frozen set, `cli.py --eval --live`): ~93% first-pass · 100% post-repair.
- **External-agent pass-rate** (`cli.py --eval --mcp`, A4 companion): **93% (14/15)** — an external agent
  driving Ludwig over MCP matches the native first-pass rate; **the gap to native is 0** (§8 thesis
  quantified). Harness now robust to inference throttling (paces + retries throttle-shaped fails only); the
  clean run needed zero retries. Lone miss = `stair_flight`, a genuine n=1 codegen miss, not an artifact.

## Shipped (post-R34; R1–R34 = the complete/historical interaction core)
- **A1** — versioned wire contract: `schema_version` on every payload + `docs/CONTRACT.md`; plan-of-record repointed.
- **D1** — daemon hardening for embedding: `/api/health`, `/api/shutdown`, `--port 0` (ephemeral, prints `PORT=`),
  loopback `--token` guarding `/api/*`+`/out/*` (open by default).
- **Studio v2** — cockpit → viewfinder reskin (`webapp/studio.html`): full-bleed Stage, floating glass panels,
  ⌘K intent bar, two themes, permission dial. Engine wiring unchanged. `prototype/` retired; `/` serves the Studio.
- **A2** — MCP server (`cli.py mcp`, `agent/mcp.py`): `ludwig_compile`/`verify`/`build`/`export`. Gate met (real
  client compiled a verified bracket → STEP).
- **A3** — Op-API over MCP + the permission gate (`agent/permissions.py`, `standards.yaml: permissions`,
  `/api/permissions` + the Studio dial). Headless-correct ("confirm" = explicit re-call). Enforced in the one
  shared write path (`build_from_ops`).
- **A4** — the demo, the docs, the second number. **Runnable** walkthrough (`examples/mcp_walkthrough.py`)
  drives the real stdio server through the whole trust arc (verify → build+inverse → reject a `rm -rf /` op
  → critic catches a 0.5 mm wall → export refused → confirmed export writes STEP), asserting each invariant,
  token-free. `docs/MCP.md` leads with the one command. `--eval --mcp` hardened against throttling →
  **external-agent pass-rate 93% (14/15), gap-to-native 0** (FINDINGS). GTM motion in `docs/GTM.md`.
  Public-demo runtime **verified** end-to-end (DEPLOY.md); deploy needs only cloud creds.
- **A5 (infra)** — repair corpus (`store/repairs.py`): remembered (critic-failure→fix) pairs, mined from
  `eval/pool.py` (disjoint from the frozen set), injected into the repair prompt. Flag-gated
  `memory.repair_corpus`, **default OFF and UNMEASURED** — it flips default-on only if an on/off eval moves
  repair rounds/rate (the measurement is Tier-1 below). `cli.py --mine-repairs` builds it.
- **Critic hardening** — the dimensional check self-verifies an element's registered extents when a brief
  declares no dims (gallery seeds, adopt, bare compile), so the headline check runs green instead of a
  vacuous n/a; the Studio bracket now shows dimensional verified.
- **Cleanup** — deleted the inert Blender render backend (`backends/render*`, ~535 lines) and the unwired
  `store/db.py` stub (both recoverable at `mesh-era-m4`); halved MCP export latency (single execute+verify);
  removed 4 dead `standards.yaml` keys; de-duped the diff/repair-hint helpers. Selftest **88/88**.

## Remaining plan — prioritized by leverage (one session = one PR; `--selftest` green, token-free)
*Ordered by value toward the north-star (deploy → distribution → revenue), not strict roadmap sequence.
Each item: why-now · gate. Pick the top unblocked item each session. Specs stay BRIEF/HARNESS_BRIEF/MACOS.*

### Tier 0 — needs the human (unblocks everything downstream)
- **Deploy the public demo.** Runtime is verified (DEPLOY.md); only cloud creds are missing.
  `gcloud run deploy ludwig-demo --source . --region europe-west1 --memory 2Gi --allow-unauthenticated`.
  THE traffic unlock — the demo-led GTM motion can't start without a URL.
- **5–10 ICP intros** (mechanical/hardware). The proof sheet + the runnable MCP walkthrough support outreach.

### Tier 1 — close the open loops (do first; mostly token-bounded)
- **A5 measurement.** `cli.py --mine-repairs` seeds `store/repairs.sqlite` from the pool; then
  `--eval --live --repair` with `LUDWIG_REPAIR_CORPUS=on` vs `off`. Record avg repair rounds + post-repair
  rate in FINDINGS; flip `memory.repair_corpus` default only if it moves a number. *Gate:* honest on/off delta.
- **Foreign-hand shared-daemon seam** (the last honest deferral, design brief §1.1). The stdio MCP server is
  a separate process from the Studio's HTTP daemon, so an external agent's ops can't paint in the Studio
  Activity Rail. MCP-over-HTTP (reuse the daemon) or a stdio→daemon proxy; SSE events gain a `client` field.
  *Gate:* an op driven over MCP appears in the Studio rail tagged by client.

### Tier 2 — the biggest new-audience capability (token-cheap, high visible value)
- **A7 — STL backend + `critic/printability.py`** (min-wall per process, overhang vs threshold, bed-contact,
  envelope from standards; registered per [H4]). Opens the 3D-print self-serve wedge — the largest audience,
  a regime the critic is strongest in. *Gate:* a 0.4 mm wall fails with the right message; repair fixes it;
  the STL opens in a slicer.
- **A8 — pack format + `packs/print3d/`.** Extract the Agent-Skills pack format from the *working* print
  domain (SKILL.md to agentskills.io spec; loader deep-merges standards, registers the critic, adds briefs —
  no loop change). *Gate:* `--pack print3d` changes critic behavior with zero loop changes; the same folder
  loads in Claude Code and lifts an external agent's first-pass on print briefs.

### Tier 3 — deepen the core + surface the packs
- **A6 — precedent store** (FTS5 over past programs → top-k few-shot into codegen, flag-gated). The lever for
  the *first-pass* number (A5 was for repair). Payload gains `precedents[]` (unblocks the Studio "informed by"
  line). *Gate:* measured first-pass delta; FINDINGS either way.
- **A9 — pack surfacing** in Studio (the deferred pack-indicator slot) + CLI `--pack`; per-pack Ambient labels.
- **A10 — [decision] second pack:** `joinery` (kozijnen/ramen/deuren) vs retro-fit `precast`, from A8 findings.

### Tier 4 — the signed desktop app (D-series; parallel, only needs a stable daemon)
- **D2** PyInstaller onedir daemon (pinned CPython) · **D3** Tauri shell (spawn onedir, ephemeral port+token,
  splash, reap; Studio forwards the token) · **D4** external-tool detection + honest no-model state · **D5**
  sign+notarize in CI · **D6** macOS chrome (menu bar, ⌘1–4, native dialogs, theme auto-switch) · **D7**
  updater + v0.2.0.

### Housekeeping (fold into whichever session touches the area)
- Fold fresh-compile into the Studio ⌘K intent bar (via `/api/compile_stream`), then retire
  `webapp/index.html` (demoted to `/index.html`).
- *(A4 nice-to-haves)* an opencode cross-provider `--eval --mcp` run (proves provider-blindness) + an
  asciinema/GIF of `examples/mcp_walkthrough.py` for GTM.

## Working conventions (don't relitigate)
- Ship to `main` directly (one deliverable per commit), push often, `--selftest` green every step.
- Real kernel gate needs the venv: `.venv/bin/python cli.py --selftest` (~88 checks) and `pytest`.
- MCP needs the SDK (`pip install mcp`); imported lazily so the spine stays green without it.
- Measure, don't assert — every store/claim gets a FINDINGS entry + a kill criterion.
