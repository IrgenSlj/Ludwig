---
name: product-render
engine: blender
scenario: studio product visualization
outputs: png, glb
requires_standards: units
example_prompt: a ceramic coffee mug, studio product render
---

# Product render skill

Make a single hero object read as a real, premium product shot.

- Compose with `L_autocam` so the subject fills the frame; avoid empty margins.
- Light with `L_studio_lights()` + `L_backdrop()` (seamless sweep) or `L_lighting("studio")`
  — a warm key paired with a cool fill so colour survives instead of washing out.
- Ground the subject with `L_seat(*objs)`; it must rest on the floor, never float or sink.
- Give every named material a real `L_pbr` surface; no flat single-hue plastic look.
- Honour every named colour / material / style word in the brief — brief fidelity is
  the measured quality bottleneck (docs/FINDINGS.md). No stray display props (plinths,
  pedestals) the brief did not ask for.
