# Contributing to Ludwig

Thanks for your interest! Ludwig is early and the surface area for high-impact
contributions is large.

## The highest-leverage contribution: toolkit capabilities

Ludwig's quality is gated by what the generated code *can call*. Every helper added
to [`ludwig_blender_lib.py`](ludwig_blender_lib.py) lifts the quality of every
render at once. Great first contributions:

- New `L_pbr` material `kind`s (brushed metal, marble, velvet, frosted glass…).
- New `L_lighting` moods or a true HDRI-based rig.
- Geometry helpers: lofts, lathes, arrays, fillets, asset import.
- Better `L_autocam` framing heuristics (rule-of-thirds, subject-aware angles).

### Toolkit ground rules

- **Headless-safe.** No operators that need a 3D viewport context; prefer building
  data directly (`bpy.data.*`, `mesh.from_pydata`) over `bpy.ops` where possible.
- **Degrade gracefully.** Wrap version-sensitive Blender API calls in `try/except`
  so the script never hard-crashes a render.
- **Name ground/backdrop objects `L_ground*`** so `L_autocam` excludes them.

## How to test a change

```bash
python3 ludwig.py "a sculptural ceramic teapot, studio product render" -c 3 -r 2
```

Inspect `renders/*.py` (every candidate's scene script is saved) and the rendered
PNGs. A good change should make the critic's scores trend up and remove a class of
recurring complaint.

## Architecture in one paragraph

`ludwig.py` is the orchestrator: it calls the `claude` CLI to generate scene code,
runs Blender headless to render, calls Claude again (with image-reading) to
critique, and loops a judge panel until a quality bar is met.
`ludwig_blender_lib.py` is the realism toolkit prepended to every generated scene.

## Code style

Match the surrounding code: small focused functions, clear names, comments that
explain *why*. Keep Python dependencies near zero.

## License

By contributing you agree your contributions are licensed under Apache-2.0.
