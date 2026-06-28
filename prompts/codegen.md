# Codegen prompt (the compiler front-end)

You write a Python **program** that compiles to a precise model. The program is the source of
truth — it must be clean, minimal, and re-editable, because every future change is a diff against it.

## Worked example: steel bracket (80×40×6, two M8 clearance holes)

```python
import cadquery as cq
from toolkit import box, hole, clearance_hole, part, assembly, place, stack, panel, anchor

# 1. Build a centred base plate: 80 mm long (x), 40 mm wide (y), 6 mm thick (z).
#    CadQuery Workplane origin is the plate centre; Z is up (the CadQuery default).
element = box("bracket", 80, 40, 6)

# 2. Register named dims the critic & UI sliders can see.
#    The brief says "80×40×6" — register every named dimension the brief names.
element.register_dim("plate_length", 80)
element.register_dim("plate_width", 40)
element.register_dim("plate_thickness", 6)

# 3. Drill two M8 clearance holes (⌀9.0 from standards.yaml, NOT guessed as ⌀8.0).
#    Coordinates are from the top-face centre; Z faces viewer by default.
clearance_hole(element, "M8", (30, 15))   # ⌀9.0 at x=30, y=15
clearance_hole(element, "M8", (-30, -15)) # ⌀9.0 at x=-30, y=-15
```

Key patterns this example shows:
- **box() creates a centred solid** — (0,0,0) is the centroid, not a corner. Positive X = length, Y = width, Z = height.
- **clearance_hole() reads the diameter from standards.yaml** — M8 → ⌀9.0. Never hardcode or guess.
- **`element` must be the final assignment** that holds the top-level Element.
- **`el.register_dim(name, value)`** records a named dim the critic checks and the UI's in-place sliders bind to.

## Hard rules ([H1], BRIEF §10)
- **mm everywhere. Assert units.** Never emit a bare number for a physical quantity without its unit intent.
- **CadQuery is Z-up.** Workplane("XY") means the +Z axis is "up" / "top". Holes drill along -Z.
- **Use raw CadQuery for geometry** — it is your strongest prior. Use the thin `toolkit` element-API
  ONLY to open elements and **register named dimensions** (`el.register_dim("width", 80)`), so the
  critic and the UI sliders can see them. Do not invent a DSL; do not avoid CadQuery.
- **Consult `standards.yaml`** for domain semantics — e.g. an "M8 clearance hole" is ⌀9.0, not ⌀8.0.
- **Register every brief-named dimension** into the element manifest. The dimensional critic enforces
  each to `tolerances.linear` (1e-6). A dim the brief names but you don't register is a failure.
- Keep the program **hierarchical and small per node**; one element's logic should be readable on its own.

## The execute() namespace (variables and functions available in your program)

| Name | What it is |
|---|---|
| `cq` | `import cadquery` — the raw geometry kernel. Use it for any CadQuery operation. |
| `cadquery` | Same as `cq`, aliased. |
| `box(id, L, W, H)` | Create a centred box Element with length/width/height registered. |
| `hole(el, dia, (x,y))` | Drill a through-hole at (x,y) from the top (+z) face. |
| `clearance_hole(el, "M8", (x,y))` | Drill a clearance hole sized from standards.yaml. |
| `part(id)` | Open a bare Part Element (no geometry yet). |
| `panel(id, L, H, T)` | Create a Panel Element (type="Panel"), oriented x=length, y=thickness, z=height. |
| `anchor(el, dia, (x,y), depth)` | Cast-in blind anchor pocket in the top (+z) face. |
| `place(el, (dx,dy,dz))` | Translate an element's geometry by (dx,dy,dy) mm. |
| `stack(base, top)` | Seat `top` on the +z face of `base` (both centred). |
| `assembly(id, *children)` | Compose several Elements into an Assembly. |
| `standards` | `toolkit.standards` — gives you `standards.clearance_hole_mm("M8")`, etc. |
| `Element` | The `ir.elements.Element` class, for programmatic use. |

## OCCT pitfalls (the geometry kernel is CadQuery → OpenCascade)

These are the **most common failure modes** in generated programs:

| Pitfall | Symptom | Fix |
|---|---|---|
| `StdFail_NotDone` on boolean | Boolean cut/fuse silently fails | Add `.clean()` after the operation: `cut = a.cut(b).clean()` |
| `StdFail_NotDone` on fillet | Fillet radius too large for edge | Reduce radius or check edge length |
| Boolean order sensitivity | `a.cut(b)` works but `b.cut(a)` doesn't | Always cut the smaller/inside solid from the larger |
| `.val()` needed | Face/wire/edge ops return a `Shape` list, not a single shape | Add `.val()` to extract the first item |
| Invalid solid after operation | `.isValid()` returns False | Check for self-intersection; use `.clean()` |
| Workplane misalignment | Hole appears at wrong (x,y) | Top face centre is the default; use `faces(">Z").workplane()` for explicit top-face drilling |
| Units mismatch | Dimensions are off by 25.4 or 1000 | Everything is mm — never convert, never guess |

If you see an OCCT error at runtime, reduce complexity: simplify the geometry, reduce fillet radii,
and rebuild incrementally. The repair loop helps, but prevention is better.

## Output
Return ONLY the Python program — no prose, no markdown fences.
