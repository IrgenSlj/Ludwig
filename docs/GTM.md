<!-- Go-to-market + business thesis. Grounded in 2025–26 competitive/pricing research (sources inline).
Internal strategy doc — substance over polish. Revisit when the demo has real usage data. -->

# Ludwig — wedge, business model, and the path to revenue

## Thesis (one line)
**Generation is commoditizing; correctness is not.** Sell *verified fabricability* — the deterministic
critic + exact OCCT B-rep + one-click dimensioned STEP/DXF/IFC — not text-to-geometry.

## The wedge
No one couples all four: **(a) exact OCCT B-rep + (b) a deterministic DFM/fabricability critic + (c)
one-click dimensioned DXF/STEP/IFC + (d) live no-LLM parametric editing.** AI-CAD startups (Zoo, Adam,
Leo — all funded in 2023–25) emit *unverified* geometry; CAD incumbents (Fusion, Onshape, SolidWorks)
don't *auto-verify fabricability* and aren't AI-native. Ludwig is the **trusted, DFM-verified STEP/DXF/IFC
generator** that feeds the rest of the chain (Xometry/SendCutSend quotes, precast CNC lines, BIM models).

## Why now / the moat
- **Generation is racing to commodity.** Autodesk is shipping *editable-B-rep foundation models* +
  text→geometry inside Fusion; Zoo/Adam/Leo are funded. Betting on "better text→CAD" is betting against
  incumbents' distribution + owned kernels.
- **The durable moat is trust.** A deterministic critic + `standards.yaml` (M8 → ⌀9.0, AD-K, min-wall,
  anchor cover) + exact B-rep *guarantees the output is fabricable and shop-ready*. That's the thing
  buyers can't get from an AI that hallucinates geometry, and that incumbents don't auto-provide.
- **BYO-inference = structurally low COGS.** Users bring their own AI key; we never resell tokens. The
  whole edit→verify→derive loop is no-LLM (R3–R9), so the product — and its public demo — is ~free to run.

## ICP & beachhead (sequence)
1. **Mechanical engineers / hardware startups** (paying $680–4,700/seat/yr today for Fusion/Onshape/
   SolidWorks; 30 min–5 hr per drawing, heavy revision churn). Wedge: intent → verified STEP + dimensioned
   drawing in seconds, re-promptable. Leo (enterprise logos) and Adam (unsolicited term sheets) prove
   budget + investor appetite are real.
2. **Job / laser-waterjet / machine shops.** Quoting is already free (SendCutSend, Xometry $686M FY25);
   their pain is *bad incoming files*. Ludwig produces their **input** — a clean, DFM-checked DXF/STEP —
   not their commodity. Partner/integrate rather than compete.
3. **Precast / structural detailers.** Tekla proves high willingness-to-pay for *detailing automation*
   (shop drawings, BOM, CNC), but it's locked-in and not AI-native. Our IFC + conventioned-drawing engine
   is the opening. Bigger deals, longer cycle — pursue after 1–2 land.

## Product surfaces (the funnel)
- **Free public demo** (`LUDWIG_DEMO=1`): load a part, drag dimensions, download a verified STEP — no
  signup, no AI, ~$0/visitor. *This is the distribution engine* (see below).
- **Local / open-core, BYO key**: the full thing incl. generation ("describe a part"). Open-core builds
  trust + a contributor moat on the substrate we don't want forked out from under us.
- **Hosted Pro / Team** (the paid tier): cloud workspace, part/version library, shared standards.yaml,
  batch + API, priority backends (IFC4precast, conventioned drawings), SSO/support.

## Business model — options weighed
| Model | For | Pro | Con | Call |
|---|---|---|---|---|
| **Per-seat SaaS** ($40–120/seat/mo) | engineers/teams | predictable; matches incumbent budgets (Fusion $680/yr ≈ $57/mo) | seat-gating fights a solo/indie wedge | **primary** |
| **Usage / API** (per verified artifact or per compile) | shops, pipelines, integrators | aligns price to value (a verified fab file); Zoo prices $/min | metering friction; commoditizable | **secondary** (API tier) |
| Perpetual desktop (Plasticity-style, $149–299) | indie/hobby | one-time; offline | no recurring; weak for teams | later/community |
| Marketplace take-rate (Xometry-style) | parts-on-demand | huge TAM | not our business; needs supply network | **no** (partner instead) |

**Pick:** open-core + **per-seat Hosted Pro** as the revenue spine, with a **usage-priced API** for shops/
integrators who want "verified DXF/STEP as a service." Free demo + local BYO as the top of funnel.

## Distribution / GTM motion
1. **Demo-led.** Ship the free demo (done — `Dockerfile` + `DEPLOY.md`, Cloud Run ~$0/mo). One sharable
   URL: "drag this bracket, download a fab-ready STEP." It proves the magic with zero cost/risk.
2. **Wedge content.** Side-by-side "AI-CAD gives you a pretty mesh; Ludwig gives you a DFM-verified STEP +
   dimensioned DXF." Post where the ICP lives (r/MechanicalEngineering, hardware/maker, precast forums).
3. **5–10 design partners** from ICP #1: real parts, measure time saved vs their CAD + drawing workflow.
   Convert to paid Pro pilots; use the verified-output angle as the close.
4. **Shop/integrator API** once a part library exists: "verified DXF/STEP endpoint" feeding quote/CNC.

## 30 / 60 / 90 (to first revenue)
- **30:** deploy the free demo to a real URL; instrument it (loads, edits, STEP downloads). Land 5
  design-partner conversations from ICP #1. *(Deploy + outreach need the human — see Asks.)*
- **60:** Hosted Pro MVP (auth + a saved part/version library + BYO-key generation). 2–3 paid pilots.
- **90:** usage-priced verified-artifact API; first integrator conversation; iterate pricing on real data.

## Biggest risk + mitigation
**Risk:** Autodesk/Zoo commoditize text→editable-B-rep from inside their stack (distribution + owned
kernels) while our substrate (CadQuery/build123d/OCCT) is freely forkable.
**Mitigation:** don't compete on generation. Win a *specific, defensible workflow*: verified fabricability
+ conventioned shop drawings + IFC/BIM detailing — the parts incumbents don't auto-verify and AI-CAD
startups don't produce. Get a beachhead's standards + workflow embedded before they ship theirs.

## Asks (need the human — physical-world / accounts / money)
- A domain + a Cloud Run (or Hetzner) deploy of the demo image (I can't hold cloud creds / can't deploy).
- 5–10 ICP intros for design partners.
- A call on pricing anchors once the demo has usage data.

## Sources
Zoo pricing/KCL; Autodesk Fusion AI + foundation models; Adam (TechCrunch, YC W25); Leo AI ($9.7M);
Onshape/Fusion/SolidWorks seat pricing; Xometry FY2025 ($686.6M); SendCutSend instant-quote; Tekla
precast detailing; CadQuery/build123d/OCP. (Full URLs in the research briefings that produced this doc.)
