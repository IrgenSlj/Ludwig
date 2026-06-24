"""Load skills (folders with SKILL.md) and standards (portable markdown).

Skills are code-adjacent docs; standards are files a non-coder can edit (BRIEF.md §2.5).
Both feed the prompt stack. The frontmatter parser is intentionally tiny — simple
``key: value`` lines between ``---`` fences, no external YAML dependency.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
STANDARDS_DIR = _ROOT / "standards"
SKILLS_DIR = _ROOT / "skills"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Tolerates a missing frontmatter block."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, parts[2].lstrip("\n")


def load_standards(names: list[str]) -> dict[str, str]:
    """Read ``standards/<name>.md`` for each requested standard that exists."""
    out: dict[str, str] = {}
    for name in names:
        p = STANDARDS_DIR / f"{name}.md"
        if p.exists():
            out[name] = p.read_text()
    return out


def available_standards() -> list[str]:
    if not STANDARDS_DIR.exists():
        return []
    return sorted(p.stem for p in STANDARDS_DIR.glob("*.md"))


def load_skill(name: str) -> dict | None:
    """Load a skill folder: returns {name, meta, body} or None if absent."""
    p = SKILLS_DIR / name / "SKILL.md"
    if not p.exists():
        return None
    meta, body = parse_frontmatter(p.read_text())
    return {"name": name, "meta": meta, "body": body}


def available_skills() -> list[str]:
    if not SKILLS_DIR.exists():
        return []
    return sorted(d.name for d in SKILLS_DIR.iterdir()
                  if (d / "SKILL.md").exists())
