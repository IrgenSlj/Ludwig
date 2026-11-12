from pathlib import Path

import pytest

from ludwig.model import ElementType, Severity, Side
from ludwig.rules.packs import PackError, RuleKind, load_pack

PACK_YAML = """\
name: test-pack
version: 0.1.0
description: test
match_tolerance_mm: 10
"""

LIMITS_YAML = """\
sash:
  max_width_mm: 1500
  max_height_mm: 2600
"""

CHECKS_YAML = """\
- id: sash-width-max
  kind: require
  applies_to: {side: erp, type: window_sash}
  require: width_mm <= limits.sash.max_width_mm
  severity: blocker
  message: "Sash {mark}: width {width_mm} mm exceeds machine limit {limits.sash.max_width_mm} mm"

- id: erp-width-matches
  kind: compare
  applies_to: {type: frame}
  left: architect.width_mm
  right: erp.width_mm
  tolerance: 1
  severity: blocker

- id: model-vs-schedule-count
  kind: consistent
  applies_to: {side: architect, type: [frame, door_leaf]}
  group_by: mark
  field: quantity
  severity: warning

- id: fire-door-has-rating
  kind: require
  when: props.fire_rating_min > 0
  require: is_set(props.burglary_class) or parent.width_mm > 0
  severity: info
"""


def make_pack(tmp_path: Path, checks: str = CHECKS_YAML, pack: str = PACK_YAML,
              limits: str | None = LIMITS_YAML) -> Path:  # fmt: skip
    (tmp_path / "pack.yaml").write_text(pack)
    (tmp_path / "checks.yaml").write_text(checks)
    if limits is not None:
        (tmp_path / "limits.yaml").write_text(limits)
    return tmp_path


def test_spec_example_pack_loads(tmp_path):
    pack = load_pack(make_pack(tmp_path))
    assert (pack.name, pack.version, pack.match_tolerance_mm) == ("test-pack", "0.1.0", 10.0)
    assert pack.limit("sash.max_width_mm") == 1500
    assert [r.id for r in pack.rules] == [
        "sash-width-max", "erp-width-matches", "model-vs-schedule-count", "fire-door-has-rating",
    ]  # fmt: skip
    req, cmp, cons, guarded = pack.rules
    assert req.kind is RuleKind.REQUIRE and req.severity is Severity.BLOCKER
    assert req.applies_to(Side.ERP, ElementType.WINDOW_SASH)
    assert not req.applies_to(Side.ARCHITECT, ElementType.WINDOW_SASH)
    assert (cmp.left, cmp.right, cmp.tolerance) == ("architect.width_mm", "erp.width_mm", 1.0)
    assert cons.types == {ElementType.FRAME, ElementType.DOOR_LEAF}
    assert guarded.when is not None and req.line == 1 and cmp.line == 8


def _bad(tmp_path, checks, match, line=None, **kw):
    with pytest.raises(PackError, match=match) as info:
        load_pack(make_pack(tmp_path, checks, **kw))
    if line is not None:
        assert info.value.line == line, str(info.value)
    return info.value


def test_unknown_rule_key_fails_with_file_and_line(tmp_path):
    checks = "- id: a\n  kind: require\n  require: width_mm > 0\n  severity: info\n  requires: x\n"
    err = _bad(tmp_path, checks, "unknown key 'requires'", line=5)
    assert str(err).startswith(str(tmp_path / "checks.yaml") + ":5:")


def test_bad_expression_fails_with_line(tmp_path):
    checks = "- id: a\n  kind: require\n  severity: info\n  require: width_mm = 3\n"
    _bad(tmp_path, checks, "bad expression", line=4)


@pytest.mark.parametrize(
    ("checks", "match"),
    [
        ("- id: a\n  kind: require\n  severity: info\n  require: widht_mm > 0\n",
         "unknown name 'widht_mm'"),
        ("- id: a\n  kind: require\n  severity: info\n  require: limits.sash.max > 0\n",
         "unknown limit 'limits.sash.max'"),
        ("- id: a\n  kind: require\n  severity: info\n  require: props.colour == \"red\"\n",
         "unknown property 'colour'"),
        ("- id: a\n  kind: require\n  severity: info\n  require: __import__(\"os\")\n",
         "bad expression"),
        ("- id: a\n  kind: require\n  severity: fatal\n  require: true\n", "severity must be"),
        ("- id: a\n  kind: check\n  severity: info\n", "kind must be"),
        ("- id: a\n  kind: require\n  severity: info\n", "missing key 'require'"),
        ("- id: Bad_Id\n  kind: require\n  severity: info\n  require: true\n", "bad id"),
        ("- id: a\n  kind: require\n  severity: info\n  require: true\n"
         "- id: a\n  kind: require\n  severity: info\n  require: true\n", "duplicate id"),
        ("- id: a\n  kind: require\n  severity: info\n  require: true\n  applies_to: {sde: erp}\n",
         "unknown key 'sde' in applies_to"),
        ("- id: a\n  kind: require\n  severity: info\n  require: true\n"
         "  applies_to: {type: door}\n",
         "type must be one of"),
        ("- id: a\n  kind: compare\n  severity: info\n  left: width_mm\n  right: erp.width_mm\n",
         "compare paths start with"),
        ("- id: a\n  kind: compare\n  severity: info\n  left: architect.width_mm\n"
         "  right: erp.width_mm\n  tolerance: -1\n", "tolerance must be"),
        ("- id: a\n  kind: compare\n  severity: info\n  left: architect.width_mm\n"
         "  right: erp.width_mm\n  require: true\n", "unknown key 'require' for a compare"),
        ("- id: a\n  kind: consistent\n  severity: info\n  group_by: mark\n  field: colour\n",
         "unknown name 'colour'"),
        ("- id: a\n  kind: require\n  severity: info\n  require: true\n  message: \"{colour}\"\n",
         "unknown placeholder"),
        ("- id: a\n  kind: require\n  severity: info\n  require: [true\n", "not valid YAML"),
        ("id: a\n", "must be a list"),
        ("- just text\n", "must be a mapping"),
    ],
)  # fmt: skip
def test_bad_checks_fail_at_load(tmp_path, checks, match):
    _bad(tmp_path, checks, match)


@pytest.mark.parametrize(
    ("pack", "match"),
    [
        ("name: x\nversion: 1\n", "version is required"),
        ("name: x\nversion: '1'\nauthor: me\n", "unknown key 'author'"),
        ("name: x\nversion: '1'\nfiles: {rules: r.yaml}\n", "unknown key 'rules' in files"),
        ("name: x\nversion: '1'\nmatch_tolerance_mm: lots\n", "must be a number"),
    ],
)
def test_bad_pack_yaml_fails_at_load(tmp_path, pack, match):
    _bad(tmp_path, CHECKS_YAML, match, pack=pack)


def test_missing_checks_file_fails(tmp_path):
    (tmp_path / "pack.yaml").write_text(PACK_YAML)
    with pytest.raises(PackError, match="file not found"):
        load_pack(tmp_path)


def test_limits_file_is_optional_when_no_rule_uses_it(tmp_path):
    checks = "- id: a\n  kind: require\n  severity: info\n  require: width_mm > 0\n"
    assert load_pack(make_pack(tmp_path, checks, limits=None)).limits == {}


def test_expressions_are_read_as_written_not_as_yaml_values(tmp_path):
    checks = "- id: a\n  kind: require\n  severity: info\n  require: true\n"
    assert load_pack(make_pack(tmp_path, checks)).rules[0].require.text == "true"
    _bad(tmp_path, "- id: a\n  kind: require\n  severity: info\n  require: yes\n",
         "unknown name 'yes'")  # fmt: skip


def test_unmatched_rules_take_type_only(tmp_path):
    from ludwig.rules.packs import PackError, load_pack

    (tmp_path / "pack.yaml").write_text("name: t\nversion: '1'\n")
    (tmp_path / "checks.yaml").write_text(
        "- id: m\n  kind: unmatched\n  missing_on: erp\n  severity: blocker\n"
        "  when: is_set(mark)\n"
    )
    with pytest.raises(PackError, match="checks.yaml:5: unmatched checks take"):
        load_pack(tmp_path)
    (tmp_path / "checks.yaml").write_text(
        "- id: m\n  kind: unmatched\n  missing_on: nowhere\n  severity: blocker\n"
    )
    with pytest.raises(PackError, match="missing_on must be one of architect, erp"):
        load_pack(tmp_path)


def test_content_hash_follows_verdict_files_not_fixtures(tmp_path):
    import shutil

    from ludwig.rules.packs import load_pack

    demo = Path(__file__).resolve().parent / "packs" / "demo"
    copy = tmp_path / "demo"
    shutil.copytree(demo, copy)
    first = load_pack(copy).content_hash
    assert first.startswith("sha256:") and first == load_pack(demo).content_hash
    (copy / "fixtures" / "extra.txt").write_text("x")
    assert load_pack(copy).content_hash == first
    limits = copy / "limits.yaml"
    limits.write_text(limits.read_text().replace("1500", "1501"))
    assert load_pack(copy).content_hash != first
