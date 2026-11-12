"""Read and change the numbers in a pack's limits.yaml without a text editor (PLAN 5.6).

Only existing numeric values change; keys, comments and layout stay as written, so the
file remains the readable source of truth. Every change is checked by loading the pack.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ludwig.rules.packs import Pack, PackError, load_pack


@dataclass
class Limit:
    """One numeric value in limits.yaml."""

    path: str  # dotted, without the `limits.` prefix
    value: float | int
    line: int
    note: str = ""  # the comment at the end of its line
    used_by: list[str] = field(default_factory=list)


def _file(pack: Pack) -> Path:
    return pack.root / "limits.yaml"


def _leaves(node: yaml.Node, prefix: str = "") -> list[tuple[str, yaml.ScalarNode]]:
    out: list[tuple[str, yaml.ScalarNode]] = []
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            out += _leaves(value, f"{prefix}{key.value}.")
    elif isinstance(node, yaml.ScalarNode):
        out.append((prefix.rstrip("."), node))
    return out


def _number(text: str) -> float | int | None:
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _note(line: str) -> str:
    head, sep, tail = line.partition(" #")
    return tail.strip() if sep and head.count('"') % 2 == 0 else ""


def read(pack: Pack) -> list[Limit]:
    """The numeric limits of a pack, in file order, with the rules that use each."""
    path = _file(pack)
    if not path.exists():
        return []
    text = path.read_text()
    root = yaml.compose(text)
    if root is None:
        return []
    lines = text.splitlines()
    users: dict[str, list[str]] = {}
    for rule in pack.rules:
        names = set()
        for expr in (rule.when, rule.require):
            if expr is not None:
                names |= {n for n in expr.names if n.startswith("limits.")}
        if rule.tolerance_limit:
            names.add(rule.tolerance_limit)
        names |= {n for n in _placeholders(rule.message) if n.startswith("limits.")}
        for name in names:
            users.setdefault(name[len("limits.") :], []).append(rule.id)
    out = []
    for dotted, node in _leaves(root):
        value = _number(node.value) if node.style is None else None
        if value is None:
            continue
        line = node.start_mark.line
        used = sorted(users.get(dotted, []))
        out.append(Limit(dotted, value, line + 1, _note(lines[line]), used))
    return out


def _placeholders(message: str) -> list[str]:
    import re

    return re.findall(r"\{([^{}]*)\}", message or "")


def update(pack: Pack, values: dict[str, float | int]) -> Pack:
    """Write new values for existing limits and return the reloaded pack; raises ValueError.

    Nothing is written unless the whole pack still loads with the new values.
    """
    path = _file(pack)
    current = {limit.path: limit for limit in read(pack)}
    unknown = sorted(set(values) - set(current))
    if unknown:
        raise ValueError(f"unknown limits: {', '.join(unknown)}")
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    nodes = dict(_leaves(yaml.compose(text)))
    for dotted, value in values.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{dotted}: a number is needed")
        node = nodes[dotted]
        start, end = node.start_mark, node.end_mark
        if start.line != end.line:
            raise ValueError(f"{dotted}: value spans lines; edit the file by hand")
        written = str(int(value)) if float(value).is_integer() else repr(float(value))
        line = lines[start.line]
        lines[start.line] = line[: start.column] + written + line[end.column :]
        # Later values on the same line shift; recompose after each change.
        text = "".join(lines)
        nodes = dict(_leaves(yaml.compose(text)))
        lines = text.splitlines(keepends=True)
    with tempfile.TemporaryDirectory() as tmp:
        trial = Path(tmp) / "pack"
        shutil.copytree(pack.root, trial, ignore=shutil.ignore_patterns("fixtures"))
        (trial / "limits.yaml").write_text(text)
        try:
            load_pack(trial)
        except PackError as exc:
            raise ValueError(str(exc).replace(str(trial), str(pack.root))) from None
    part = path.with_suffix(".yaml.part")
    part.write_text(text)
    os.replace(part, path)
    return load_pack(pack.root)
