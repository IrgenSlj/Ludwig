"""No-model tests for the v2 harness config resolver + telemetry store (M1, WS0-adapted).

Pure stdlib — no kernel, no API calls (docs/V2_ROADMAP.md §5 testing strategy).
"""
from __future__ import annotations

import pytest

from agent.config import HarnessConfig, SearchConfig, load_config
from telemetry.store import RunStore


def test_defaults_resolve():
    c = HarnessConfig()
    assert (c.search.depth, c.search.branch, c.search.keep_k) == (3, 3, 1)
    assert c.search.veri_ratio == 0.5
    assert c.budget.max_calls == 60
    assert c.telemetry.enabled is True and c.telemetry.runs_dir == "runs"


def test_reads_ludwig_toml(tmp_path):
    toml = tmp_path / "ludwig.toml"
    toml.write_text(
        "[search]\ndepth = 4\nbranch = 2\nveri_ratio = 0.7\n[budget]\nmax_calls = 20\n",
        encoding="utf-8",
    )
    c = load_config(toml)
    assert c.search.depth == 4 and c.search.branch == 2 and c.search.veri_ratio == 0.7
    assert c.budget.max_calls == 20
    # unspecified keys keep their defaults
    assert c.search.keep_k == 1 and c.budget.cost_confirm_usd == 5.0


def test_missing_file_is_all_defaults(tmp_path):
    assert load_config(tmp_path / "nope.toml").config_hash() == HarnessConfig().config_hash()


def test_unknown_toml_keys_ignored(tmp_path):
    toml = tmp_path / "ludwig.toml"
    toml.write_text("[search]\ndepth = 5\nfuture_key = 99\n", encoding="utf-8")
    c = load_config(toml)   # forward-compatible: unknown key dropped, not an error
    assert c.search.depth == 5


def test_cli_overrides_coerce_by_type():
    c = load_config(overrides={"search.depth": "5", "budget.max_calls": "30",
                               "telemetry.enabled": "false"})
    assert c.search.depth == 5 and isinstance(c.search.depth, int)
    assert c.budget.max_calls == 30
    assert c.telemetry.enabled is False


def test_config_hash_stable_and_sensitive():
    assert HarnessConfig().config_hash() == HarnessConfig().config_hash()
    changed = load_config(overrides={"search.depth": 9})
    assert changed.config_hash() != HarnessConfig().config_hash()
    assert len(HarnessConfig().config_hash()) == 12


@pytest.mark.parametrize("bad", [
    {"search.veri_ratio": 2.0},
    {"search.veri_ratio": -0.1},
    {"search.depth": 0},
    {"search.branch": 0},
    {"budget.max_calls": 0},
])
def test_validation_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        load_config(overrides=bad)


def test_unknown_override_key_raises():
    with pytest.raises(KeyError):
        load_config(overrides={"search.nonexistent": 1})


def test_search_config_validate_directly():
    with pytest.raises(ValueError):
        SearchConfig(veri_ratio=1.5).validate()


def test_runstore_roundtrips(tmp_path):
    rs = RunStore("run_abc", runs_dir=tmp_path)
    rs.write_manifest({"config_hash": "deadbeef", "seed": 0})
    rs.extend_events([{"type": "brief", "text": "bracket"},
                      {"type": "selection", "kept": "b1"}])
    assert rs.read_manifest()["run_id"] == "run_abc"
    assert rs.read_manifest()["config_hash"] == "deadbeef"
    assert [e["type"] for e in rs.read_events()] == ["brief", "selection"]


def test_runstore_media_content_addressed(tmp_path):
    rs = RunStore("run_media", runs_dir=tmp_path)
    a = rs.put_media(b"same-bytes", ext="png")
    b = rs.put_media(b"same-bytes", ext="png")   # identical → dedup to one file, same digest
    c = rs.put_media(b"other-bytes", ext="png")
    assert a == b and a != c
    assert rs.media_path(a).exists() and rs.media_path(c).exists()
    assert len(list(rs.media_dir.glob("*.png"))) == 2


def test_runstore_empty_reads(tmp_path):
    rs = RunStore("empty", runs_dir=tmp_path)
    assert rs.read_events() == [] and rs.read_manifest() is None
