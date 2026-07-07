# Ludwig — Design Brief: Studio v2 (Claude Design handoff)

*Extends docs/UX_BRIEF.md — the Stage & Director paradigm, the art direction tokens, and the five
surfaces are UNCHANGED and remain the constitution. This brief adds what the agentic-harness
direction (HARNESS_BRIEF.md) and the macOS app (docs/MACOS_APP_PLAN.md) require the interface to
express. Everything here binds to seams that already exist in the engine (or land in the A-series)
— nothing in this brief may invent a UI that requires faking a capability.*

> North star unchanged: **Mies — "less is more." A viewfinder, not a cockpit.**
> The new tension this brief resolves: the Studio is no longer the only client of the engine —
> **other agents work here too.** The interface must make foreign hands visible, reviewable, and
> calm.

---

## 1. What Studio v2 must newly express (four additions, in priority order)

### 1.1 The Foreign Hand — external agents made visible (binds to: MCP server, A2–A4)
When Claude Code / opencode / another harness drives Ludwig over MCP, their work must appear in
the **same Activity Rail** as Ludwig's own agent — never a second rail, never a separate window.
Design language:
- Each activity entry carries a small **origin mark**: Ludwig's own loop (unmarked, the default) vs
  an external client (a hairline-bordered chip with the client name — "Claude Code", "opencode").
  Origin is metadata on an event, not a new layout.
- External **plans** arrive as the same Plan/Build chips shipped in R24: op summaries with
  Accept / Reject. In Plan mode (permissions), foreign ops *wait*; in Build mode they stream. The
  permission mode must be visible at a glance (a single small state indicator near the Rail — not
  a modal, not a banner).
- **Export requests from foreign hands always surface a confirmation** — this is the pre-export
  gate made visible. The confirmation shows the critic verdict inline (the Ambient palette:
  teal-green / amber / red) so approving is informed, one glance, one click.
- Anti-goal: a "chat with the agent" pane. The Rail shows *work*, not conversation ("you glance at
  it; you don't live in it" — UX_BRIEF §3 stands).

### 1.2 Packs — the domain made legible (binds to: pack loader, A8–A9)
- A **pack indicator** lives where a document's "paper size" would in a drafting app: quiet,
  peripheral, always true. Switching packs is deliberate (a small menu), never a prominent tab bar
  — packs are context, not navigation.
- Ambient Correctness gains **per-pack check labels**: hovering an amber element in the `print3d`
  pack reads "wall 0.4 mm < FDM min 0.8 mm", in `precast` "anchor cover 32 mm < 40 mm". Same
  palette, same calm; the *words* carry the domain.
- The critic report panel groups checks by source (core geometry / dimensional / pack), hairline
  rules only. No badges, no iconography zoo.

### 1.3 Memory — recall as a moment, not a panel (binds to: precedent store, A5–A6)
- When codegen used a precedent, the result carries a single quiet line: *"informed by:
  ⟨part name, date⟩"* — clickable, opens the precedent read-only beside the Stage (a light
  comparison state, not a diff editor). If no precedent was used, nothing appears. Memory earns
  pixels the same way it earns bytes: only when it did something.
- No "memory manager" screen in v2. Deleting/inspecting stores stays in the CLI until real usage
  demands more.

### 1.4 The permission surface (binds to: standards.yaml permissions block, A3)
Three tiers, shown as one control: **Auto** (param edits apply live), **Plan** (all ops wait for
Accept), **Locked** (read-only — for reviewing someone else's model). The control's design should
borrow from camera mode-dials, not from settings panels: physical, small, always-visible,
impossible to be confused about. Export confirmation exists in all tiers.

## 2. macOS-native direction (binds to: D-series, docs/MACOS_APP_PLAN.md)

The Tauri shell wraps the same webapp — so "native" is achieved through *behavioral* fidelity, not
by re-platforming the UI. Design obligations:

- **Window chrome:** hiddenTitleBar / overlay traffic lights over the Stage's top-left; the Intent
  Bar summons with ⌘K (Raycast muscle memory), never a persistent search field. Full-screen and
  split-view must behave (the Stage reflows; rails collapse gracefully at <1000 px width).
- **Menu bar is real:** File (New, Open Recent, Export…), Edit (Undo = inverse-op, Redo), View
  (representation switcher items with shortcuts: ⌘1 3D, ⌘2 plan, ⌘3 section, ⌘4 drawing), Window,
  Help. Every menu item maps to an existing endpoint — the menu is a third client of the daemon,
  not decoration.
- **Keyboard-first parity:** every signature interaction reachable without the mouse. Document the
  map in a single ⌘/ overlay.
- **System integration:** respect the OS light/dark → paper-light / graphite-dark themes
  (auto-switch, with manual override); native file dialogs for export; drag a STEP/IFC out of the
  artifact list straight into Finder; proper dock badge only for a *blocked* agent (never for
  routine progress).
- **Feel targets:** launch-to-Stage under 3 s after first run (splash covers daemon boot —
  design the splash: the wordmark on paper, a single hairline progress rule, nothing animated for
  animation's sake); window resize never stutters the viewport (three.js canvas letterboxes during
  live resize if needed).

## 3. Explicitly unchanged (do not redesign)
- The five Director surfaces (Stage, Intent Bar, Activity Rail, Point-to-Navigate, Ambient
  Correctness) — extend, never rearrange.
- Art direction tokens: near-monochrome, amber/red/teal-green reserved for the critic, humanist
  grotesque + drafting mono, drawing line-weight hierarchy, two calm themes, motion-as-meaning.
- Graceful crystallization remains the P2–P3 signature; nothing in v2 fakes it early ([H3]).
- The representation switcher's physicality (section plane sweeps the solid).

## 4. Deliverables requested from Claude Design
1. **Foreign-hand states** — the Activity Rail with mixed-origin entries; a foreign plan awaiting
   Accept; the export confirmation with inline critic verdict. (Highest priority — it is the demo.)
2. **The permission mode-dial** — three tiers, both themes, keyboard interaction.
3. **Pack indicator + per-pack Ambient hover language** — print3d and precast examples.
4. **The precedent moment** — the "informed by" line and the read-only comparison state.
5. **macOS chrome pass** — traffic-light overlay, menu-bar map, ⌘K Intent Bar, the splash,
   window-resize behavior spec, ⌘/ shortcut overlay.
6. **The no-model state** — the Studio with no inference CLI detected: every token-free lane fully
   alive (sliders, face-drag, sections, exports), the Intent Bar carrying one quiet "connect a
   model" affordance. This state must read as *a working precision tool*, never as a crippled
   trial — it is the product truth (verified CAD works without any AI) made visible.
7. **The first-run moment** — cold launch on a clean machine: splash → Stage with the seed part
   already adopted (the vendored bracket, per R1), a single unobtrusive orientation hint pointing
   at the Intent Bar, gone forever after first dismissal. No tour, no coach marks, no modal.
8. **The app icon** — Ludwig.app per the art direction: the wordmark/mark on paper or graphite,
   Braun-honest, legible at 16 px, both light and dark dock treatments. Replaces the placeholder
   icons in `desktop/src-tauri/icons/`.
9. **A degradation spec** — how every new surface behaves at 900×600 (the minimum window).

## 5. Seam contract (Code-side obligations these designs may assume)

| Design surface | Engine seam | Status |
|---|---|---|
| Foreign-hand origin marks | SSE events carry a `client` field | deferred (STATUS.md Tier 1 — last honest deferral) |
| Plan chips for foreign ops | Op-API `/api/plan` `/api/build` + agent_stream | shipped (R18, R23–R26) |
| Export confirmation w/ verdict | pre-export critic hook + result payload | shipped |
| Permission mode-dial | `standards.yaml: permissions` enforced server-side | A3 |
| Pack indicator / labels | pack loader; CheckResult carries source + message | A8–A9 |
| Precedent moment | result payload gains `precedents[]` | A6 |
| No-model state | `/api/health` reports detected tools (claude/opencode/Blender) | D4 |
| Menu bar / shortcuts | daemon endpoints (all exist); Tauri menu API | D-series |
| Theme auto-switch | CSS custom properties already tokenized | D-series |

*The rule from UX_BRIEF stands: if a design requires a seam that isn't real, the design waits or
the seam gets built — the UI never fakes the engine.*
