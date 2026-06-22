#!/usr/bin/env python3
"""
Ludwig — an AI-native 3D design tool (prototype slice, hardened loop).

Pipeline per round:
    generate N diverse candidate scenes  (Claude writes Blender Python)
        -> render each in headless Blender
        -> cheaply reject empty/void renders (PIL variance check)
        -> Claude *views* and scores each survivor
        -> keep the best; if it clears the quality bar, stop
        -> else regenerate variations informed by the winner's critique

Inference runs through the locally-authenticated `claude` CLI: no API key,
nothing to pay per token. "Bring your own Claude."

Usage:
    python3 ludwig.py "a cozy scandinavian reading nook at golden hour"
    python3 ludwig.py "a brutalist concrete chair" --candidates 3 --rounds 3 --target 8
"""

import argparse
import concurrent.futures as cf
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
RENDERS = os.path.join(ROOT, "renders")


def _find_blender():
    """Locate the Blender executable cross-platform.

    Honors $BLENDER_PATH, then PATH, then common install locations.
    """
    if os.environ.get("BLENDER_PATH"):
        return os.environ["BLENDER_PATH"]
    on_path = shutil.which("blender")
    if on_path:
        return on_path
    candidates = [
        "/Applications/Blender.app/Contents/MacOS/Blender",
        *sorted(glob.glob("/Applications/Blender*.app/Contents/MacOS/Blender"), reverse=True),
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/snap/bin/blender",
        *sorted(glob.glob(r"C:\Program Files\Blender Foundation\*\blender.exe"), reverse=True),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


BLENDER = _find_blender()

# The realism toolkit is prepended to every generated scene script, so its
# L_* helpers are in scope for the model-written code.
with open(os.path.join(ROOT, "ludwig_blender_lib.py")) as _f:
    BLENDER_LIB = _f.read()

try:
    from PIL import Image, ImageStat
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# --------------------------------------------------------------------------- #
# Inference: the locally-authenticated `claude` CLI is our LLM engine.
# --------------------------------------------------------------------------- #

def claude(prompt, *, allow_read=False, timeout=240, retries=2):
    """Call `claude -p` headlessly, with retry/backoff on transient failures."""
    cmd = ["claude", "-p", prompt]
    if allow_read:
        cmd += ["--allowedTools", "Read"]
    last = ""
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
            last = proc.stderr.strip() or "empty response"
        except subprocess.TimeoutExpired:
            last = f"timed out after {timeout}s"
        if attempt < retries:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"claude CLI failed after {retries + 1} attempts: {last}")


def preflight():
    """Fail fast with a helpful message if the two engines aren't available."""
    problems = []
    if not BLENDER or not os.path.exists(BLENDER):
        problems.append(
            "Blender not found. Install it, or set BLENDER_PATH to the executable, "
            "e.g.\n    export BLENDER_PATH=/path/to/blender")
    if not shutil.which("claude"):
        problems.append(
            "The `claude` CLI was not found on PATH. Install it from "
            "https://claude.com/claude-code and run `claude` once to log in.")
    if problems:
        sys.exit("Ludwig preflight failed:\n\n- " + "\n- ".join(problems))


# --------------------------------------------------------------------------- #
# Step 1: natural language -> Blender Python (design-as-code core)
# --------------------------------------------------------------------------- #

CODEGEN_BRIEF = textwrap.dedent("""\
    You are Ludwig's geometry engine. You translate a creative brief into ONE
    self-contained Blender 5 Python (bpy) script that BUILDS A 3D SCENE.

    A realism toolkit is ALREADY IMPORTED and in scope. USE IT — do not hand-roll
    materials, lights, world, camera or ground. Available helpers:

      L_reset()                         # clear the scene (call this FIRST)
      L_pbr(name, color=(r,g,b), kind)  # -> Material. kind in: wood, fabric,
                                        #   leather, ceramic, metal, plaster,
                                        #   concrete, plastic, glass
      L_apply(obj, material)            # assign material + bevel + smooth shading
      L_ground(size, color, kind)       # add a floor (kind e.g. 'wood','concrete')
      L_lighting(mood)                   # complete balanced light rig. mood in:
                                        #   golden_hour, sunset, midday, overcast,
                                        #   studio, dramatic, night
      L_autocam(azimuth_deg, elevation_deg, lens)  # auto-FITS the subject in frame
      L_camera(location, target, lens)  # manual camera (use only if you need it)

    Hard rules — follow ALL of them:
    - Output ONLY Python code. No prose, no markdown fences, no explanation.
    - Call L_reset() first. Build the subject from primitives/meshes near the
      WORLD ORIGIN (within ~6 units of (0,0,0)), visibly sized, and assign every
      mesh a material via L_apply(obj, L_pbr(...)).
    - Compose each object from MULTIPLE well-proportioned parts that connect
      cleanly — NO single blocky cubes, NO floating/disconnected pieces. Parts
      that belong together must touch and align. Seat everything on the ground.
    - Give distinct objects distinct base colors and material kinds so the image
      has color variety (don't make everything one hue).
    - Call L_ground(...) unless the brief implies no floor.
    - Set mood with ONE call to L_lighting('<mood>'). Do NOT hand-tune sun/sky/fill.
      Pick the mood that matches the brief (e.g. 'golden_hour', 'studio', 'night').
    - CAMERA: call L_autocam(azimuth_deg=..., elevation_deg=...) — it auto-fits the
      whole subject in frame, so just choose a flattering ANGLE. Prefer a 3/4 view
      (azimuth ~30-50) at a low-to-moderate elevation (~12-25) over a flat frontal
      product shot. This removes the #1 failure (bad crops).
    - Do NOT call bpy.ops.render.*, do NOT set render.filepath/resolution/engine —
      Ludwig owns rendering. Build only the scene + camera + lights.
    - Must run headlessly in `blender --background` with no errors.
""")

VARIANTS = [
    "Interpretation A: clean and minimal, restrained palette, generous negative space.",
    "Interpretation B: warmer and more detailed, richer materials, dramatic key light.",
    "Interpretation C: a bolder camera angle (lower or 3/4 view) and stronger contrast.",
    "Interpretation D: a more graphic, stylized composition with confident color.",
]


def generate_scene_code(brief, *, variant=None, critique=None, prior_code=None, error=None):
    parts = [CODEGEN_BRIEF, f"\nCREATIVE BRIEF:\n{brief}\n"]
    if variant is not None:
        parts.append(f"\nTake this distinct creative direction:\n{VARIANTS[variant % len(VARIANTS)]}\n")
    if error and prior_code:
        parts.append(
            "Your previous script raised an error in Blender. Fix it and return the "
            f"full corrected script.\n\nERROR:\n{error}\n\nPREVIOUS SCRIPT:\n{prior_code}\n"
        )
    elif critique and prior_code:
        parts.append(
            "An art director reviewed the best render so far. Produce a NEW script that "
            "keeps what worked and fixes the issues. You may diverge creatively.\n\n"
            f"FEEDBACK:\n{critique}\n\nBEST SCRIPT SO FAR:\n{prior_code}\n"
        )
    return _extract_python(claude("\n".join(parts)))


def _extract_python(text):
    fence = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    idx = text.find("import bpy")
    return text[idx:].strip() if idx != -1 else text.strip()


EDIT_BRIEF = textwrap.dedent("""\
    You are Ludwig's geometry engine. Below is an existing Blender scene script.
    Apply ONLY the requested change, keeping everything else as close to identical
    as possible — same objects, layout, materials and lighting except where the
    instruction requires a change. This is a surgical edit, not a rewrite.

    The same realism toolkit (L_pbr, L_apply, L_ground, L_lighting, L_autocam,
    L_backdrop, ...) is in scope; reuse it.

    Output ONLY the full, updated Python script. No prose, no markdown fences.

    CHANGE REQUESTED:
    {instruction}

    CURRENT SCRIPT:
    {code}
""")


def edit_scene(prior_code, instruction):
    return _extract_python(claude(EDIT_BRIEF.format(instruction=instruction, code=prior_code)))


# --------------------------------------------------------------------------- #
# Step 2: execute in headless Blender + guaranteed render plumbing
# --------------------------------------------------------------------------- #

RENDER_FOOTER = textwrap.dedent("""\

    # ---- Ludwig render footer (guarantees a valid render) -------------------
    import math, mathutils
    _scene = bpy.context.scene
    if _scene.camera is None:
        L_autocam()
    if not any(o.type == 'LIGHT' for o in _scene.objects):
        L_lighting('golden_hour')
    L_quality(ENGINE, SAMPLES)
    _scene.render.resolution_x = RES_X
    _scene.render.resolution_y = RES_Y
    _scene.render.image_settings.file_format = 'PNG'
    _scene.render.filepath = OUT_PATH
    bpy.ops.render.render(write_still=True)
""")


def render(script_code, out_png, *, engine="EEVEE", samples=48, res=(960, 600)):
    header = (f"OUT_PATH = {out_png!r}\nENGINE = {engine!r}\nSAMPLES = {samples}\n"
              f"RES_X = {res[0]}\nRES_Y = {res[1]}\n")
    full = f"{BLENDER_LIB}\n\n{header}\n{script_code}\n{RENDER_FOOTER}"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(full)
        script_path = f.name
    try:
        proc = subprocess.run(
            [BLENDER, "--background", "--python", script_path],
            capture_output=True, text=True, timeout=300,
        )
        log = proc.stdout + "\n" + proc.stderr
        ok = os.path.exists(out_png) and "Error" not in proc.stderr
        return ok, log
    finally:
        os.unlink(script_path)


def _blender_error(log):
    lines = [l for l in log.splitlines()
             if "Error" in l or "Traceback" in l or l.strip().startswith("  File ")]
    return "\n".join(lines[-12:]) if lines else log[-800:]


def is_void(png, threshold=6.0):
    """Cheap pre-filter: a near-uniform image (no real subject) before any LLM call."""
    if not _HAS_PIL:
        return False
    try:
        stat = ImageStat.Stat(Image.open(png).convert("L"))
        return stat.stddev[0] < threshold
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Step 3: Claude *views* the render and scores it (the moat)
# --------------------------------------------------------------------------- #

CRITIQUE_BRIEF = textwrap.dedent("""\
    You are a world-class 3D art director. Use your Read tool to VIEW the image at:

        {png}

    The creative brief was:

        {brief}

    Grade it on FIVE axes, each 0-10, as a tough but fair and CONSISTENT grader.
    Anchor your scale: 0-2 = unreadable/broken, 3-4 = recognizable but crude,
    5-6 = decent, 7-8 = strong, 9-10 = portfolio-grade.

      FRAMING       — composition, subject fills the frame, camera angle
      LIGHTING      — mood, dimensionality, believable shadows
      MATERIALS     — surface realism and color variety (not one flat hue)
      BRIEF         — how completely it depicts what was asked for
      BELIEVABILITY — does it read as a real, coherent object/scene

    Respond in EXACTLY this format, nothing else:

    FRAMING: <0-10>
    LIGHTING: <0-10>
    MATERIALS: <0-10>
    BRIEF: <0-10>
    BELIEVABILITY: <0-10>
    KEEP: <one line on what works>
    FIXES:
    - <concrete, actionable Blender change>
    - <another concrete change>
""")

_AXES = ("FRAMING", "LIGHTING", "MATERIALS", "BRIEF", "BELIEVABILITY")


def critique(brief, png):
    # Image-reading critiques are the slow path (and slower under parallel load),
    # so give them more headroom than codegen calls.
    return claude(CRITIQUE_BRIEF.format(png=png, brief=brief), allow_read=True, timeout=420)


def _score(text):
    """Average of the rubric axes, on a 0-10 scale (rounded to 1 decimal)."""
    vals = []
    for axis in _AXES:
        m = re.search(rf"{axis}:\s*(\d+(?:\.\d+)?)", text)
        if m:
            vals.append(min(10.0, float(m.group(1))))
    if not vals:
        m = re.search(r"SCORE:\s*(\d+)", text)  # backward-compatible fallback
        return float(m.group(1)) if m else 0.0
    return round(sum(vals) / len(vals), 1)


# --------------------------------------------------------------------------- #
# Candidate worker: gen -> render -> (self-repair) -> void check -> critique
# --------------------------------------------------------------------------- #

def evaluate_candidate(brief, png, *, variant=None, seed_code=None, seed_critique=None):
    code = generate_scene_code(brief, variant=variant, critique=seed_critique, prior_code=seed_code)
    ok, log = render(code, png)
    if not ok:
        code = generate_scene_code(brief, prior_code=code, error=_blender_error(log))
        ok, log = render(code, png)
    # Persist every candidate's scene script next to its render for debugging.
    with open(png.replace(".png", ".py"), "w") as f:
        f.write(code)
    if not ok:
        return {"code": code, "png": None, "score": -1,
                "critique": "render failed", "note": _blender_error(log)[:300]}
    if is_void(png):
        return {"code": code, "png": png, "score": 0,
                "critique": "SCORE: 0\nKEEP: nothing\nFIXES:\n- empty/void frame; subject not in camera view"}
    crit = critique(brief, png)
    return {"code": code, "png": png, "score": _score(crit), "critique": crit}


# --------------------------------------------------------------------------- #
# Orchestrator: panel of candidates, score-gated rounds
# --------------------------------------------------------------------------- #

def run(brief, *, candidates, rounds, target, workers):
    os.makedirs(RENDERS, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", brief.lower())[:40].strip("-")
    best = None

    for rnd in range(1, rounds + 1):
        seed_code = best["code"] if best else None
        seed_critique = best["critique"] if best else None
        print(f"\n=== Round {rnd}/{rounds}  (panel of {candidates}) ===")

        tasks = []
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for c in range(candidates):
                png = os.path.join(RENDERS, f"{slug}_r{rnd}_c{c}.png")
                tasks.append(ex.submit(
                    evaluate_candidate, brief, png,
                    variant=c, seed_code=seed_code, seed_critique=seed_critique))
            results = []
            for fut in cf.as_completed(tasks):
                r = fut.result()
                results.append(r)
                tag = os.path.basename(r["png"]) if r["png"] else "(no render)"
                print(f"  • candidate {tag}: score {r['score']}")

        round_best = max(results, key=lambda r: r["score"])
        if best is None or round_best["score"] > best["score"]:
            best = round_best
        # persist the winning scene script next to its render
        if best["png"]:
            with open(best["png"].replace(".png", ".py"), "w") as f:
                f.write(best["code"])
        print(f"  ► best so far: {best['score']}/10  →  {best['png']}")
        print(textwrap.indent(best["critique"], "    "))

        if best["score"] >= target:
            print(f"\n✓ cleared the quality bar ({best['score']} ≥ {target}).")
            break

    # Hero shot: re-render the winning scene in Cycles at higher quality.
    if best and best["png"] and best["score"] > 0:
        hero = os.path.join(RENDERS, f"{slug}_HERO.png")
        print(f"\n• rendering hero shot in Cycles → {hero}")
        ok, log = render(best["code"], hero, engine="CYCLES", samples=128, res=(1280, 800))
        if ok:
            best["hero"] = hero
            print(f"  ✓ hero: {hero}")
        else:
            print("  ! hero render failed; keeping EEVEE winner.")
            print(_blender_error(log)[:300])

    print(f"\nWinner: {best['png']}  (score {best['score']}/10)")
    print("Renders in:", RENDERS)
    return best


def run_edit(from_path, instruction):
    """Re-prompt an existing scene: apply a surgical change and re-render.

    This is Ludwig's core advantage — the design is editable code, not an opaque
    mesh. "Same, but taller / in brass / from a lower angle" is a re-prompt.
    """
    os.makedirs(RENDERS, exist_ok=True)
    with open(from_path) as f:
        prior = f.read()
    base = os.path.splitext(os.path.basename(from_path))[0]
    slug = re.sub(r"[^a-z0-9]+", "-", instruction.lower())[:30].strip("-")
    out = os.path.join(RENDERS, f"{base}__edit_{slug}.png")

    print(f"• editing {os.path.basename(from_path)}: “{instruction}”")
    code = edit_scene(prior, instruction)
    ok, log = render(code, out)
    if not ok:
        code = edit_scene(code, "Fix this Blender error and keep the change:\n"
                          + _blender_error(log))
        ok, log = render(code, out)
    with open(out.replace(".png", ".py"), "w") as f:
        f.write(code)
    if not ok:
        print("  ✗ edit render failed:\n" + _blender_error(log)[:400])
        return
    hero = out.replace(".png", "_HERO.png")
    render(code, hero, engine="CYCLES", samples=128, res=(1280, 800))
    print(f"  ✓ edited render → {out}\n  ✓ hero → {hero}")


def main():
    ap = argparse.ArgumentParser(description="Ludwig — AI-native 3D design (hardened loop)")
    ap.add_argument("brief", nargs="?", help="natural-language description of the scene")
    ap.add_argument("--edit", "-e", metavar="INSTRUCTION",
                    help="re-prompt an existing scene (requires --from)")
    ap.add_argument("--from", dest="from_path", metavar="SCENE.py",
                    help="path to an existing renders/*.py scene to edit")
    ap.add_argument("--candidates", "-c", type=int, default=3, help="scenes per round (default 3)")
    ap.add_argument("--rounds", "-r", type=int, default=3, help="max refinement rounds (default 3)")
    ap.add_argument("--target", "-t", type=float, default=8, help="stop when best score ≥ this (default 8)")
    ap.add_argument("--workers", "-w", type=int, default=3, help="parallel candidate workers (default 3)")
    ap.add_argument("--quick", "-q", action="store_true",
                    help="fast single-shot: 1 candidate, 1 round (great for iterating)")
    args = ap.parse_args()

    preflight()
    t0 = time.time()
    if args.edit:
        if not args.from_path:
            ap.error("--edit requires --from <scene.py>")
        run_edit(args.from_path, args.edit)
    elif args.brief:
        candidates = 1 if args.quick else args.candidates
        rounds = 1 if args.quick else args.rounds
        run(args.brief, candidates=candidates, rounds=rounds,
            target=args.target, workers=args.workers)
    else:
        ap.error("provide a brief, or use --edit INSTRUCTION --from SCENE.py")
    print(f"Elapsed: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
