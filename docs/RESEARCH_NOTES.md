# RESEARCH_NOTES.md — deliberative-design-harness mechanisms for Ludwig's CAD substrate

Purpose: source notes for building WS1/WS2/WS4/WS6, and for choosing a launch benchmark.
Scope: retrofit academic "deliberative design harness" mechanisms onto Ludwig's typed IR over
CadQuery/OCCT B-rep + deterministic geometric critic. NOT Blender.
Convention per section: **mechanism → quantified result (or "unverified") → transfer-to-Ludwig line.**
Numbers are as reported by the cited source. Some cited papers use model names dated later than
their substance (env date is 2026-07); those are flagged where they matter. Not fabricated.

---

## 1. BlenderGym (CVPR 2025 Highlight) — the core WS2 search mechanism
arXiv 2504.01786 · Gu, Huang, Je, Yang, Guibas (Stanford) · blendergym.github.io

**Mechanism — pruned d×b tree search over candidate edits ("propose–verify–improve"):**
- Each node runs a brainstormer→code-editor pipeline that emits an executable edit (a script/diff).
- **Breadth b**: repeat that pipeline independently `b` times → `b` parallel edit proposals per level.
  Paper uses **b = 4**.
- **Depth d**: iterate the whole propose→select loop `d` times; last iteration's winner is the output.
  Paper uses **d = 3**.
- **Verifier-driven pruning**: split the `b` candidates into `b/2` sequential pairs; the verifier picks
  a winner per pair (pairwise, not absolute); aggregate winners and repeat pairwise selection until one
  remains. That winner seeds the next depth level.
- **Verifier scaling knob `k`**: re-run the whole selection `k` times, reshuffling the candidate list
  each time, to spend more compute on verification of the same candidate set (a self-consistency vote).

**VeriRatio + the "Goldilocks" budget-split result (the load-bearing finding for WS2):**
- **VeriRatio = verification queries / total queries.** Tested at 0.33, 0.62, 0.73.
- The optimal VeriRatio *rises with total compute budget* (Table 2, as extracted):
  - `<30` queries → 0.33 best; `30–60` → 0.33–0.62; `60–100` → 0.62+; `>100` → **0.73 best**.
- Headline: **at large budgets, moving compute from generation to verification wins.** A *scaled*
  open-source verifier (InternVL2-8B) reported to **outperform unscaled/lightly-scaled GPT-4o and
  Claude-3.5-Sonnet verifiers on all three task metrics**; raising verifier reselection `k` from 1→64
  monotonically pulled the selected edit closer to goal (Fig. 5). Verifier compute complements — and at
  scale beats — generator compute.

**Transfer to Ludwig:** implement WS2 as a d×b tree over IR-level candidate edits (each node = a
re-promptable ProgramNode diff), pruned by pairwise selection. Ludwig's advantage: the "verifier" can be
the *deterministic* critic over exact B-rep (cheap, exact) instead of a VLM — so the VeriRatio budget is
near-free and we can sit at the high-verification end of the curve by default. Budget-split math is the
tuning surface: escalate breadth/depth with the difficulty tier; spend the freed budget on more critic
passes / more candidate generation, not on a bigger generator.

---

## 2. VIGA (2026) — interleaved analysis-by-synthesis with full trajectory in context (WS1)
arXiv 2601.11109 · "Vision-as-Inverse-Graphics Agent via Interleaved Multimodal Reasoning"
· fugtemypt123.github.io/VIGA-website

**Mechanism:** a training-free code→render→inspect loop that keeps the *full multimodal trajectory*
in context — plans, code diffs, and render history in an "evolving context memory" — rather than a
stateless or summarized iteration. One agent alternates **generator** and **verifier** roles ("skill
library"): propose executable code that edits the scene, render, inspect the visual discrepancy, feed
that back as the next edit's grounding. Interleaves image and text reasoning tokens across steps.

**Quantified result (relative gain over one-shot baselines, as reported):**
- BlenderGym **+35.32%**, SlideBench **+117.17%**, their new BlenderBench **+124.70%**.
- These are relative improvements vs one-shot; absolute scores/definitions not fully extracted here →
  treat the exact figures as **author-reported, not independently verified.**

**Transfer to Ludwig:** WS1 = keep the *whole* repair trajectory (prompt, each IR diff, each critic
report, each render/section) in the loop context, not a summary. The generate→verify→repair loop already
has this shape; the delta is (a) never summarizing away prior diffs+critic findings, and (b) letting the
inspection signal be the deterministic critic report (numeric, exact) plus optional render, so "inspect
discrepancy" is a measured residual, not a VLM guess.

---

## 3. IR3D-Bench (NeurIPS 2025 D&B) — VLMs fail precise spatial/numeric control (WS5)
arXiv 2506.23329 · "Evaluating VLM Scene Understanding as Agentic Inverse Rendering"
· ir3d-bench.github.io · github.com/LiuHengyu321/IR3D-Bench

**Mechanism/setup:** give a VLM an image, ask it to emit a Blender script that reconstructs the scene
(agentic inverse rendering), then score geometry, spatial relations, appearance, plausibility. Built on
CLEVR val (15,000 synthetic images, 3–10 objects, full 3D/material annotations).

**Result:** models reliably infer *what* an object is and *where* its center is, but **fail at "how
large" and "how" objects relate in 3D** — i.e., precise size/pose/relational numeric control is the
failure mode. Motivates a symbolic layer over the VLM.

**Transfer to Ludwig:** this is the external evidence for Ludwig's thesis — **Ludwig already IS the
symbolic layer.** Precision (exact dims, tolerances, relations) must live in the typed IR + deterministic
critic over exact B-rep, never in the VLM's spatial estimate. Use IR3D-Bench as the citation for "why a
symbolic/parametric substrate is required," and keep vision demoted to soft/aesthetic per BRIEF §10.

---

## 4. LLM-as-judge integrity / reward-hacking (2025–26) (WS4)
Key sources: arXiv 2504.14716 (COLM 2025); 2409.15268 "Style Outweighs Substance"; 2410.02736
"Justice or Prejudice?"; 2602.02219 / 2601.13649 (pairwise position/language bias); 2602.18037
(gradient reg vs reward hacking).

**Mechanisms / findings:**
- **Pairwise vs absolute is a real trade.** Pairwise tracks human preference better *but is more
  exploitable*: under an injected distractor feature, **pairwise preferences flip in ~35% of cases vs
  ~9% for absolute scores** (2504.14716). So pairwise buys fidelity at the cost of manipulability.
- **Reward hacking is fast and measurable.** Without regularization a generator drives judge score
  sharply up while held-out accuracy peaks early and then decouples — the judge is being gamed
  (2602.18037). Style/verbosity/position biases let substance-free answers win (2409.15268, 2410.02736).
- **Mitigations in the literature:** cross-model judging (judge ≠ generator family), position/order
  randomization, honeypot/distractor probes to detect gaming, rubric grounding, and preferring a
  *verifiable* reward over a learned judge wherever one exists.

**Transfer to Ludwig:** WS4 should lean on the fact that Ludwig has a **verifiable reward** (the
deterministic critic over exact B-rep) — use it as the primary signal and treat any VLM judge as soft,
pairwise, aesthetic-only (already the BRIEF §10 stance). Where a VLM judge is used: (1) never same-family
as the generator, (2) randomize pair order, (3) seed honeypot candidates (known-bad edits) to detect a
gamed judge, (4) prefer pairwise for aesthetic ranking but keep an absolute deterministic gate in front
so a flipped pairwise call can never pass a geometrically-wrong part.

---

## 5. CAD code-generation benchmarks — launch-scorecard candidates (WS6 / GTM)

We will **not** use BlenderGym as the scorecard (Blender scene benchmark, wrong substrate). The CAD-native,
execution-verified options below. "Stock LLM" = non-fine-tuned frontier model. Metrics glossary:
*IR/Invalidity* = fraction that fail to execute/produce degenerate solid; *IoU* = voxel volumetric overlap;
*CD* = Chamfer distance between point clouds (lower better); *F1/Feature-F1* = feature match.

### 5a. Query2CAD (arXiv 2406.00144)
- **Measures:** does the generated **FreeCAD Python macro** produce the specified model. Success is
  exact-match; "any deviation is a failure." Eval is **manual** (human check), with VQAScore≥0.9 only as
  an auto *stopping* criterion for the self-refine loop.
- **Data:** small — **57 queries** (~21 easy / 20 medium / 16 hard). Backend = FreeCAD macros.
- **Stock baselines:** GPT-4-Turbo **53.6%** first-pass → **76.7%** after 3 self-refine iters;
  GPT-3.5-Turbo **32.7%** → **53.4%**; CodeLlama-70B effectively unusable.
- **License:** "open-sourced data/model/code" (GitHub) but **no explicit license stated** → unverified.
- **Verdict:** good difficulty-tiering idea and a real first-pass number, but **too small (57) and
  manual eval** → not a defensible public scorecard on its own; FreeCAD backend ≠ our CadQuery/OCCT stack.

### 5b. CAD-Coder (arXiv 2505.14646 · MIT DeCoDE · github.com/anniedoris/CAD-Coder)
- **Measures:** **valid-syntax/compile rate** + **IoU (best & median)** of generated **CadQuery** vs GT.
- **Data:** GenCAD-Code — DeepCAD/Text2CAD retargeted to **~110K verified text↔CadQuery↔3D triplets**
  (8K high / 70K med / 32K hard) + ~1.5K CoT samples; VLM (image→code).
- **Result:** fine-tuned CAD-Coder **IoU_best 0.675**, beats all open models (~+60% over next open) and
  all closed models tested (next-best GPT-4.5 is 0.151 IoU lower); 100/100 test subset produced
  error-free CadQuery. **Stock-LLM absolute numbers not cleanly extractable from the PDF here →
  unverified beyond "GPT-4.5 ≈ 0.524 IoU_best (0.675−0.151)".**
- **License:** arXiv non-exclusive; code on GitHub; **model/dataset license not explicitly stated** →
  partly unverified.
- **Verdict:** **substrate-matched (CadQuery/OpenCascade)** and uses exactly our metrics (compile rate,
  IoU). Strong reference for target metrics; dataset large enough to sample a held-out eval set.

### 5c. CADSmith (arXiv 2603.26512 · github.com/jabarkle/CADSmith)
- **Mechanism (this is a *system* + its 100-prompt bench):** multi-agent CadQuery generation with two
  nested loops — inner loop fixes execution errors; **outer loop = programmatic geometric validation from
  the OpenCASCADE kernel** (bbox dims, volume, solid validity) + an independent VLM judge. RAG over API
  docs, not fine-tuning. **This is essentially Ludwig's architecture described in a paper.**
- **Data/metrics:** custom **100 prompts, 3 tiers (T1–T3)**; metrics = execution rate, F1, IoU, Chamfer.
- **Result (best vs base ablation):** execution **95% → 100%**; median F1 **0.9707 → 0.9846**; median
  **IoU 0.8085 → 0.9629**; mean **Chamfer 28.37 → 0.74**.
- **License:** GitHub repo (license not confirmed here → unverified).
- **Verdict:** best *architectural* precedent (OCCT-exact outer-loop validation = our deterministic
  critic). Bench is small (100) and custom → good as an internal regression harness, weak as a public
  leaderboard.

### 5d. BenchCAD (arXiv 2605.10865 · HF + GitHub)
- **Measures:** 4 tasks — **Vision2Code (img→CadQuery)**, Code-Edit (instruction-guided, normalized
  accuracy), Vision-QA, Code-QA. Vision2Code metrics = **voxel IoU, Chamfer, Hausdorff, Feature-F1,
  essential-op recall, execution rate**.
- **Data:** **17,900 execution-verified CadQuery programs across 106 industrial part families** (bevel
  gears, springs, twist drills…), shipping parametric source + STEP + multi-view renders + params + op
  lists. Real engineering parts, not toy sketch-extrude.
- **Stock MLLM baselines on Vision2Code (as reported; model names are env-dated):** Claude-Opus-class
  IoU **0.267** / exec **90.4%**; Gemini-Pro-class IoU **0.279** / exec **79.8%**; GPT-5-class IoU
  **0.207** / exec **67.5%**; a *trained* small Qwen3-VL IoU **0.752** / exec **98.9%**. Takeaway: **stock
  frontier models sit at IoU ~0.2–0.3 with 68–90% execution** — low geometric fidelity, the open gap.
- **License:** **data CC-BY-4.0, eval code MIT** (clean, usable).
- **Verdict:** the **strongest public, execution-verified, CadQuery-native, industrially-relevant**
  benchmark found. Clean license, our exact substrate and metrics, ships STEP (our fab backend), and has
  an edit task (matches Ludwig's `--edit` minimal-diff thesis).

### 5e. Text2CAD-Bench (arXiv 2605.18430)
- **Measures:** **Chamfer Distance, Invalidity Rate, IoU** for L1–L3; **VLM-scored** 0–10 for L4.
- **Data:** **600 human-curated** examples, tiered **L1(200)/L2(200)/L3(100)/L4(100)**; L4 spans real
  domains (mechanical/consumer/medical/architectural). Backend = **CadQuery**.
- **Stock baselines (Geo-CD, lower better; env-dated model names, report as-is):** GPT-5-class L1 44.3 /
  L3 93.5 (IR 11%→68%); Claude-4.5-Sonnet-class L1 52.6 / L3 70.1 (IR 20%→70%); DeepSeek L1 53.2 / L3
  101.2; Qwen3-max L1 84.5 / L3 148.6. **Invalidity climbs to ~68–92% at L3** — hard geometry breaks
  stock models.
- **License:** **CC BY 4.0** (clean).
- **Verdict:** small but **human-curated, difficulty-stratified, CadQuery-native, clean license**, with a
  real-world L4 tier. Best *curated* companion to the large BenchCAD.

### 5f. Foundational datasets (not scorecards themselves, but the source pools)
- **DeepCAD** (arXiv, ~2021): **178,238** sketch-and-extrude command sequences. The base pool most
  CAD-gen work resamples. Sequence/DSL, not code; needs retargeting to CadQuery.
- **Text2CAD** (arXiv 2409.17106): DeepCAD + **~170K models / ~600K multi-level NL prompts** (beginner→
  expert). The main text↔CAD supervision source; parametric sequence backend.
- **Fusion 360 Gallery** (arXiv 2010.02392, Autodesk): **8,625 human-authored** sketch+extrude sequences +
  a reconstruction "Gym." Reported ~**67% exact reconstruction (IoU=1)** by neurally-guided search on the
  face-extrusion task. Human-designed, but DSL/sequence not code, and limited op set.
- Also seen (not deep-dived): **CAD-Recode** (point-cloud→CadQuery reverse-engineering, 2412.14042),
  **cadrille** (multi-modal CAD recon w/ RL, 2505.22914), **CAD-Judge** (fast morphological grader for
  text-to-CAD, 2508.04002 — relevant to WS4 as a CAD-specific judge), **UniCAD** (unified multi-task CAD
  benchmark, 2606.05058), **HistCAD** (constraint-aware history-based rep + bench, 2602.19171),
  **Text-to-CadQuery** (2505.06507). None clearly beats BenchCAD/Text2CAD-Bench as a launch scorecard; note
  them as expansion/secondary tasks.

---

## 6. Recommendation — launch scorecard

**Primary: BenchCAD (2605.10865).** It is the only found benchmark that is simultaneously
(a) **execution-verified and CadQuery/OpenCascade-native** — Ludwig's exact substrate; (b) **cleanly
licensed** (data CC-BY-4.0, code MIT); (c) **industrially real** (106 engineering part families, ships
STEP — our fab backend); and (d) already carries an **instruction-guided edit task**, which directly
scores Ludwig's `--edit` minimal-diff thesis. Its published stock-frontier baselines (**IoU ~0.2–0.3,
execution ~68–90%** on Vision2Code) give a wide, honest gap for a verify-and-repair compiler to close —
exactly the story Ludwig sells (verified fabricability, not text-to-CAD).

**Secondary / curated companion: Text2CAD-Bench (2605.18430).** 600 human-curated, difficulty-stratified
(L1–L4), CadQuery, CC-BY-4.0, with metrics we already compute (CD / IoU / Invalidity). Use it as the
held-out, human-trusted "hard geometry" tier where stock models hit **68–92% invalidity at L3** — the
clearest demonstration that a deterministic-critic repair loop matters.

**Target metric for the Ludwig scorecard:** report **(1) execution/valid-solid rate** and
**(2) IoU** as the headline pair (both benchmarks share them), plus **Chamfer** as the fidelity tie-breaker
and **first-pass vs after-repair** as two columns (mirrors Query2CAD's 53.6%→76.7% framing and is the
number that proves the verify→repair loop earns its compute). Keep **CADSmith** as the internal
architectural regression harness (its OCCT-exact outer loop is literally our critic), and **DeepCAD /
Text2CAD** as the sampling pools for building a private held-out eval set to prevent leaderboard overfit.

**Do not** adopt Query2CAD (57 tasks, manual eval, FreeCAD) or Fusion 360 Gallery (DSL not code, narrow
op set) as the public scorecard; cite them for lineage only.

---

### Verification / caveats
- BlenderGym Table-2 VeriRatio bucket boundaries and the InternVL2>GPT-4o claim were extracted from the
  arXiv HTML; the qualitative Goldilocks trend is solid, exact bucket edges are as-extracted.
- VIGA's +35/+117/+125% are author-reported relative gains; absolute definitions not independently
  verified.
- Several benchmarks (BenchCAD, Text2CAD-Bench) cite model names dated later than mid-2026 (GPT-5.x,
  Claude-4.5/Opus-4.7, Gemini-3.1). Reported as printed; treat specific per-model figures as
  source-reported, not re-run by us. The *ranges* (stock IoU ~0.2–0.3, high L3 invalidity) are the
  load-bearing takeaways and are consistent across sources.
- Licenses confirmed clean: BenchCAD (CC-BY-4.0 / MIT), Text2CAD-Bench (CC-BY-4.0). CAD-Coder, CADSmith,
  Query2CAD dataset licenses **unverified** (repos exist; explicit license not confirmed here).
