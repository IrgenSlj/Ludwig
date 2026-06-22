# Changelog

All notable changes to Ludwig are documented here.

## [Unreleased]

### Added
- **Core loop**: prompt → Claude writes Blender Python → headless render →
  Claude vision-critiques the render → iterate.
- **Judge panel**: N diverse candidates per round, scored on a 5-axis rubric
  (framing, lighting, materials, brief-coverage, believability), score-gated
  across rounds.
- **Realism toolkit** (`ludwig_blender_lib.py`): procedural PBR materials,
  balanced lighting presets, a studio set (seamless sweep backdrop + 3-point
  rig), and bounding-box auto-framing.
- **`--edit`**: surgically re-prompt an existing scene ("same, but taller / in
  brass") — the design-as-code editability moat.
- **`--quick`**: fast single-shot mode (1 candidate, 1 round) for iterating.
- Cycles "hero shot" re-render of the winning scene.
- Inference via the local `claude` CLI (no API key); cross-platform Blender
  detection; retrying inference with backoff; preflight checks.
- Smoke tests and CI.

### Known limitations
- Geometry is primitive-assembled — strongest on hero objects / product renders;
  complex multi-object interiors are still crude. Richer geometry helpers are on
  the roadmap.
- The critic is a tough grader; scores are a relative signal, not an absolute one.
