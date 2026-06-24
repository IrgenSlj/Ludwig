# Tolerances standard

Tolerance class is meaningful only for physical outputs (3D print / manufacture);
ignore it for pure renders.

- **loose** — decorative / display models; ±1 mm is fine.
- **standard** — functional prints with fits; ±0.2 mm; add clearance to mating parts.
- **precision** — mechanical assemblies; ±0.05 mm; call out datums and critical dims.

When tolerance is `n/a` (a render), prioritise visual believability over dimensional
exactness.
