"""Load and validate a rule pack (SPEC section 6). Every error names the file and line."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from ludwig.model import ELEMENT_FIELDS, STANDARD_PROPS, ElementType, Severity, Side
from ludwig.rules.expr import Expr, ExprError, compile_expr

_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


class RuleKind(StrEnum):
    REQUIRE = "require"
    COMPARE = "compare"
    CONSISTENT = "consistent"
    UNMATCHED = "unmatched"


_PACK_KEYS = {"name", "version", "description", "files", "match_tolerance_mm", "ids_severity"}
_FILES_KEYS = {"checks", "limits", "ids"}
_COMMON_KEYS = {"id", "kind", "applies_to", "severity", "message", "description", "when"}
_KIND_KEYS = {
    RuleKind.REQUIRE: {"require"},
    RuleKind.COMPARE: {"left", "right", "tolerance"},
    RuleKind.CONSISTENT: {"group_by", "field", "tolerance"},
    RuleKind.UNMATCHED: {"missing_on"},
}
_REQUIRED = {
    RuleKind.REQUIRE: {"require"},
    RuleKind.COMPARE: {"left", "right"},
    RuleKind.CONSISTENT: {"group_by", "field"},
    RuleKind.UNMATCHED: {"missing_on"},
}
_APPLIES_KEYS = {"side", "type"}


class PackError(ValueError):
    """A pack that cannot be loaded."""

    def __init__(self, file: Path | str, line: int | None, message: str):
        where = f"{file}:{line}" if line else str(file)
        super().__init__(f"{where}: {message}")
        self.file, self.line = str(file), line


class _LineDict(dict):
    line: int = 0
    key_lines: dict[str, int]
    raw_text: dict[str, str]


class _Loader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _Loader, node: yaml.MappingNode) -> _LineDict:
    result = _LineDict(loader.construct_mapping(node, deep=True))
    result.line = node.start_mark.line + 1
    result.key_lines = {k.value: k.start_mark.line + 1 for k, _ in node.value}
    # Expressions are compiled from the text as written: YAML would turn `true` into a bool.
    result.raw_text = {
        k.value: v.value for k, v in node.value if isinstance(v, yaml.ScalarNode)
    }
    return result


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.load(path.read_text(), Loader=_Loader)  # noqa: S506 - SafeLoader subclass
    except FileNotFoundError:
        raise PackError(path, None, "file not found") from None
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise PackError(path, mark.line + 1 if mark else None, f"not valid YAML: {exc}") from None


def _line(d: Any, key: str | None = None) -> int | None:
    if isinstance(d, _LineDict):
        return d.key_lines.get(key, d.line) if key else d.line
    return None


@dataclass(frozen=True)
class Rule:
    """One check from checks.yaml."""

    id: str
    kind: RuleKind
    severity: Severity
    message: str
    file: str
    line: int
    sides: frozenset[Side] = frozenset()
    types: frozenset[ElementType] = frozenset()
    when: Expr | None = None
    require: Expr | None = None
    left: str | None = None
    right: str | None = None
    tolerance: float = 0.0
    tolerance_limit: str | None = None  # `limits.<path>` the tolerance is read from
    group_by: str | None = None
    field: str | None = None
    missing_on: Side | None = None
    description: str = ""

    def applies_to(self, side: Side, etype: ElementType) -> bool:
        """Whether an element with this side and type is in the rule's scope."""
        return (not self.sides or side in self.sides) and (not self.types or etype in self.types)


@dataclass
class Pack:
    """A loaded, validated rule pack."""

    name: str
    version: str
    root: Path
    description: str = ""
    match_tolerance_mm: float = 0.0
    limits: dict[str, Any] = field(default_factory=dict)
    rules: list[Rule] = field(default_factory=list)
    ids_path: Path | None = None
    ids_specs: list[Any] = field(default_factory=list)
    ids_severity: Severity = Severity.WARNING
    content_hash: str = ""

    def limit(self, path: str) -> Any:
        """A value from limits.yaml by dotted path (without the `limits.` prefix)."""
        node: Any = self.limits
        for part in path.split("."):
            node = node[part]
        return node


def _limit_paths(node: Any, prefix: str = "limits") -> set[str]:
    if isinstance(node, dict):
        out: set[str] = set()
        for key, value in node.items():
            out |= _limit_paths(value, f"{prefix}.{key}")
        return out
    return {prefix}


def _element_name_error(name: str, limits: set[str]) -> str | None:
    """Names allowed in require/when: fields, props.*, limits.*, parent.<field>."""
    parts = name.split(".")
    if parts[0] == "limits":
        return None if name in limits else f"unknown limit {name!r}"
    if parts[0] == "parent":
        parts = parts[1:]
    if len(parts) == 1 and parts[0] in ELEMENT_FIELDS:
        return None
    if len(parts) == 2 and parts[0] == "props":
        return None if parts[1] in STANDARD_PROPS else f"unknown property {parts[1]!r}"
    return f"unknown name {name!r}"


def _side_name_error(name: str) -> str | None:
    """Names allowed in compare: architect.<field> or erp.<field>, incl. props."""
    parts = name.split(".")
    if parts[0] not in ("architect", "erp"):
        return f"compare paths start with architect. or erp., got {name!r}"
    return _element_name_error(".".join(parts[1:]), set())


def _expr(text: Any, file: Path, line: int | None, limits: set[str]) -> Expr:
    try:
        expr = compile_expr(text)
    except ExprError as exc:
        raise PackError(file, line, f"bad expression: {exc}") from None
    for name in sorted(expr.names):
        problem = _element_name_error(name, limits)
        if problem:
            raise PackError(file, line, problem)
    return expr


def _tolerance(raw: Any, file: Path, limits: set[str]) -> dict[str, Any]:
    """A tolerance: a number >= 0, or the name of a limit (resolved once limits are known)."""
    tolerance = raw.get("tolerance", 0)
    if isinstance(tolerance, str) and tolerance.startswith("limits."):
        if tolerance not in limits:
            raise PackError(file, _line(raw, "tolerance"), f"unknown limit {tolerance!r}")
        return {"tolerance_limit": tolerance}
    if isinstance(tolerance, bool) or not isinstance(tolerance, int | float) or tolerance < 0:
        raise PackError(file, _line(raw, "tolerance"), "tolerance must be a number >= 0 or a limit")
    return {"tolerance": float(tolerance)}


def _one_of(value: Any, enum: type[StrEnum], what: str, file: Path, line: int | None) -> Any:
    try:
        return enum(value)
    except ValueError:
        allowed = ", ".join(e.value for e in enum)
        raise PackError(file, line, f"{what} must be one of {allowed}; got {value!r}") from None


def _as_set(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _load_rule(raw: Any, file: Path, limits: set[str], seen: set[str]) -> Rule:
    line = _line(raw)
    if not isinstance(raw, dict):
        raise PackError(file, line, "each check must be a mapping")
    kind = _one_of(raw.get("kind"), RuleKind, "kind", file, _line(raw, "kind"))
    allowed = _COMMON_KEYS | _KIND_KEYS[kind]
    for key in raw:
        if key not in allowed:
            raise PackError(file, _line(raw, key), f"unknown key {key!r} for a {kind} check")
    for key in {"id", "kind", "severity"} | _REQUIRED[kind]:
        if key not in raw:
            raise PackError(file, line, f"missing key {key!r}")
    rule_id = raw["id"]
    if not isinstance(rule_id, str) or not _ID.match(rule_id):
        raise PackError(file, _line(raw, "id"), f"bad id {rule_id!r} (lower-case words and -)")
    if rule_id in seen:
        raise PackError(file, _line(raw, "id"), f"duplicate id {rule_id!r}")
    seen.add(rule_id)
    severity = _one_of(raw["severity"], Severity, "severity", file, _line(raw, "severity"))

    applies = raw.get("applies_to") or {}
    if not isinstance(applies, dict):
        raise PackError(file, _line(raw, "applies_to"), "applies_to must be a mapping")
    for key in applies:
        if key not in _APPLIES_KEYS:
            raise PackError(file, _line(applies, key), f"unknown key {key!r} in applies_to")
    sides = frozenset(
        _one_of(s, Side, "side", file, _line(applies, "side"))
        for s in _as_set(applies.get("side", []))
    )
    types = frozenset(
        _one_of(t, ElementType, "type", file, _line(applies, "type"))
        for t in _as_set(applies.get("type", []))
    )

    def text(key: str) -> Any:
        return raw.raw_text.get(key, raw[key]) if isinstance(raw, _LineDict) else raw[key]

    when = _expr(text("when"), file, _line(raw, "when"), limits) if "when" in raw else None
    fields: dict[str, Any] = {}
    names_for_message: set[str] = set(ELEMENT_FIELDS) | limits
    if kind is RuleKind.REQUIRE:
        fields["require"] = _expr(text("require"), file, _line(raw, "require"), limits)
    elif kind is RuleKind.COMPARE:
        for key in ("left", "right"):
            problem = _side_name_error(str(raw[key]))
            if problem:
                raise PackError(file, _line(raw, key), problem)
            fields[key] = raw[key]
            names_for_message.add(raw[key])
        fields.update(_tolerance(raw, file, limits))
    elif kind is RuleKind.UNMATCHED:
        if "when" in raw or "side" in applies:
            key = "when" if "when" in raw else "applies_to"
            raise PackError(file, _line(raw, key), "unmatched checks take applies_to: {type} only")
        fields["missing_on"] = _one_of(raw["missing_on"], Side, "missing_on", file,
                                       _line(raw, "missing_on"))  # fmt: skip
    else:
        fields.update(_tolerance(raw, file, limits))
        for key in ("group_by", "field"):
            problem = _element_name_error(str(raw[key]), set())
            if problem or str(raw[key]).startswith("parent."):
                raise PackError(file, _line(raw, key), problem or f"unknown name {raw[key]!r}")
            fields[key] = raw[key]

    message = raw.get("message", "")
    if not isinstance(message, str):
        raise PackError(file, _line(raw, "message"), "message must be text")
    for placeholder in _PLACEHOLDER.findall(message):
        if placeholder in names_for_message or placeholder in ("measured", "expected"):
            continue
        if placeholder.startswith("props.") and placeholder[6:] in STANDARD_PROPS:
            continue
        raise PackError(file, _line(raw, "message"), f"unknown placeholder {{{placeholder}}}")

    return Rule(
        id=rule_id,
        kind=kind,
        severity=severity,
        message=message,
        file=str(file),
        line=line or 0,
        sides=sides,
        types=types,
        when=when,
        description=str(raw.get("description", "")),
        **fields,
    )


def load_pack(root: str | Path) -> Pack:
    """Load pack.yaml, limits.yaml and checks.yaml from a pack folder; raises PackError."""
    root = Path(root)
    pack_file = root / "pack.yaml"
    meta = _read_yaml(pack_file)
    if not isinstance(meta, dict):
        raise PackError(pack_file, None, "must be a mapping")
    for key in meta:
        if key not in _PACK_KEYS:
            raise PackError(pack_file, _line(meta, key), f"unknown key {key!r}")
    for key in ("name", "version"):
        if not isinstance(meta.get(key), str) or not meta[key]:
            raise PackError(pack_file, _line(meta, key), f"{key} is required and must be text")
    files = meta.get("files") or {}
    for key in files:
        if key not in _FILES_KEYS:
            raise PackError(pack_file, _line(files, key), f"unknown key {key!r} in files")
    tolerance = meta.get("match_tolerance_mm", 0)
    if isinstance(tolerance, bool) or not isinstance(tolerance, int | float) or tolerance < 0:
        raise PackError(pack_file, _line(meta, "match_tolerance_mm"), "must be a number >= 0")

    limits_file = root / files.get("limits", "limits.yaml")
    limits = _read_yaml(limits_file) if limits_file.exists() else {}
    if limits is None:
        limits = {}
    if not isinstance(limits, dict):
        raise PackError(limits_file, None, "must be a mapping")
    limit_names = _limit_paths(limits)

    checks_file = root / files.get("checks", "checks.yaml")
    checks = _read_yaml(checks_file)
    if checks is None:
        checks = []
    if not isinstance(checks, list):
        raise PackError(checks_file, None, "must be a list of checks")
    seen: set[str] = set()
    rules = [_load_rule(raw, checks_file, limit_names, seen) for raw in checks]
    plain_limits = _plain(limits)
    for i, rule in enumerate(rules):
        if rule.tolerance_limit:
            node: Any = plain_limits
            for part in rule.tolerance_limit.split(".")[1:]:
                node = node[part]
            if isinstance(node, bool) or not isinstance(node, int | float) or node < 0:
                message = f"{rule.tolerance_limit} (tolerance of {rule.id}) must be a number >= 0"
                raise PackError(limits_file, None, message)
            rules[i] = replace(rule, tolerance=float(node))

    ids_path = root / files["ids"] if "ids" in files else None
    ids_specs = []
    if ids_path is not None:
        from ludwig.rules import ids

        try:
            ids_specs = ids.load(ids_path)
        except ids.IdsError as exc:
            raise PackError(ids_path, None, str(exc)) from None
    ids_severity = _one_of(meta.get("ids_severity", "warning"), Severity, "ids_severity",
                           pack_file, _line(meta, "ids_severity"))  # fmt: skip
    hashed = [pack_file, checks_file, limits_file, *([ids_path] if ids_path else [])]
    return Pack(
        name=meta["name"],
        version=meta["version"],
        root=root,
        description=str(meta.get("description", "")),
        match_tolerance_mm=float(tolerance),
        limits=_plain(limits),
        rules=rules,
        ids_path=ids_path,
        ids_specs=ids_specs,
        ids_severity=ids_severity,
        content_hash=content_hash(root, hashed),
    )


def content_hash(root: Path, files: list[Path]) -> str:
    """sha256 over the pack files that decide its verdicts: each file's path and bytes.

    Fixtures do not count; any byte changed in pack, checks, limits or IDS file does.
    """
    digest = hashlib.sha256()
    present = {f for f in files if f.exists()}
    for path in sorted(present, key=lambda f: f.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return "sha256:" + digest.hexdigest()


def _plain(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_plain(v) for v in node]
    return node

