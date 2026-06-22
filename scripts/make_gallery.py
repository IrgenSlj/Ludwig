#!/usr/bin/env python3
"""Generate gallery hero renders serially (gentle on the local inference engine)
and copy each to docs/gallery/<name>.png by its exact slug (no stale-hero bug)."""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GALLERY = os.path.join(ROOT, "docs", "gallery")

BRIEFS = [
    ("headphones", "a pair of premium over-ear headphones with leather earcups and an aluminium frame, studio product render"),
    ("office-chair", "a modern ergonomic office chair with a mesh back and polished aluminium base, studio product render"),
    ("macarons", "three colorful french macarons stacked on a small ceramic plate, studio product render"),
]


def slug(brief):
    return re.sub(r"[^a-z0-9]+", "-", brief.lower())[:40].strip("-")


def main():
    os.makedirs(GALLERY, exist_ok=True)
    for name, brief in BRIEFS:
        print(f"\n##### {name}: {brief}", flush=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "ludwig.py"), brief,
                        "-c", "3", "-r", "2", "-w", "2"], cwd=ROOT)
        hero = os.path.join(ROOT, "renders", f"{slug(brief)}_HERO.png")
        if os.path.exists(hero):
            shutil.copy(hero, os.path.join(GALLERY, f"{name}.png"))
            print(f"##### DONE {name} -> {hero}", flush=True)
        else:
            print(f"##### MISSING hero for {name} ({hero})", flush=True)
    print("\n##### GALLERY COMPLETE", flush=True)


if __name__ == "__main__":
    main()
