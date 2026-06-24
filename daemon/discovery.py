"""Discovery form — RULE 1: lock the brief before the model draws (BRIEF.md §2.6, §4).

A fresh request should answer a small constraint form *before* generation, so the cost
of a wrong direction is one form, not one finished model. The schema below is the
product-viz default; later verticals (CAD/BIM) extend it with stricter fields.

Until the M4 prompt-stack refactor, answers are composed into the ``brief`` string the
existing loop already consumes — no change to ``ludwig.py``.
"""
from __future__ import annotations

# Each field: name, label, type (select|text), options (for select), default, help.
DISCOVERY_SCHEMA: list[dict] = [
    {
        "name": "target_output",
        "label": "Target output",
        "type": "select",
        "options": ["render", "3d_print", "manufacture", "drawing", "bim"],
        "default": "render",
        "help": "What the design is ultimately for. Drives fidelity vs. precision.",
    },
    {
        "name": "units",
        "label": "Units",
        "type": "select",
        "options": ["mm", "cm", "m", "in", "ft"],
        "default": "cm",
        "help": "Real-world units. Guessing scale is catastrophic for CAD.",
    },
    {
        "name": "size",
        "label": "Overall size / scale",
        "type": "text",
        "default": "",
        "help": "e.g. '~30 cm tall', 'fits on a desk', '2 m wide'.",
    },
    {
        "name": "tolerance",
        "label": "Tolerance class",
        "type": "select",
        "options": ["n/a", "loose", "standard", "precision"],
        "default": "n/a",
        "help": "Only meaningful for manufacture / print; ignored for renders.",
    },
    {
        "name": "style",
        "label": "Style / reference",
        "type": "text",
        "default": "",
        "help": "e.g. 'minimalist scandinavian', 'industrial', a brand reference.",
    },
    {
        "name": "constraints",
        "label": "Hard constraints",
        "type": "text",
        "default": "",
        "help": "Non-negotiables: must-have features, materials, colors, no-gos.",
    },
]

_REQUIRED = {"target_output", "units"}
_LABELS = {f["name"]: f["label"] for f in DISCOVERY_SCHEMA}
_OPTIONS = {f["name"]: set(f.get("options", [])) for f in DISCOVERY_SCHEMA if f["type"] == "select"}


def validate(answers: dict) -> list[str]:
    """Return a list of problems; empty means the brief is lockable."""
    problems = []
    for name in _REQUIRED:
        if not answers.get(name):
            problems.append(f"missing required field: {name}")
    for name, opts in _OPTIONS.items():
        v = answers.get(name)
        if v and v not in opts:
            problems.append(f"{name!r}={v!r} is not one of {sorted(opts)}")
    return problems


def compose_brief(raw_brief: str, answers: dict | None) -> str:
    """Append a locked-constraints block to the brief for the codegen prompt."""
    if not answers:
        return raw_brief
    lines = []
    for f in DISCOVERY_SCHEMA:
        v = answers.get(f["name"])
        if v and str(v).strip() and v != "n/a":
            lines.append(f"- {f['label']}: {v}")
    if not lines:
        return raw_brief
    return raw_brief + "\n\nDesign constraints (locked — honor these exactly):\n" + "\n".join(lines)
