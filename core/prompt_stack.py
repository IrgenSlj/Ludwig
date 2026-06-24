"""Compose the codegen prompt from ordered, file-backed layers (BRIEF.md §4).

    discovery directives + identity + active standards + active skill
      + project metadata + adapter toolkit reference + the brief

Every layer is optional; empty layers are dropped. This is the real, composable stack
M3's ``compose_brief`` was a precursor to. Default standards are empty so wiring this
into generation does not change behavior until a vertical opts standards in.
"""
from __future__ import annotations

from .models import Brief


def build_prompt(
    brief: Brief,
    *,
    identity: str = "",
    standards: dict[str, str] | None = None,
    skill_body: str = "",
    toolkit_reference: str = "",
    project_meta: dict | None = None,
) -> str:
    sections: list[tuple[str, str]] = []
    if identity:
        sections.append(("IDENTITY", identity))
    if standards:
        joined = "\n\n".join(f"## {name}\n{text}" for name, text in standards.items())
        sections.append(("STANDARDS", joined))
    if skill_body:
        sections.append(("SKILL", skill_body))
    if project_meta:
        meta = "\n".join(f"- {k}: {v}" for k, v in project_meta.items() if v)
        if meta:
            sections.append(("PROJECT", meta))
    if toolkit_reference:
        sections.append(("TOOLKIT", toolkit_reference))

    body = brief.text
    if brief.discovery:
        locked = "\n".join(f"- {k}: {v}" for k, v in brief.discovery.items()
                           if v and str(v).strip() and v != "n/a")
        if locked:
            body += "\n\nDesign constraints (locked — honor these exactly):\n" + locked
    sections.append(("BRIEF", body))

    return "\n\n".join(f"=== {label} ===\n{content}" for label, content in sections)
