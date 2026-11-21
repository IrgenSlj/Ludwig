"""PLAN 6.7: a new pack release replaces the working copy and keeps the factory's limits."""

import shutil
from pathlib import Path

from ludwig import cli
from ludwig.rules import limits
from ludwig.rules.install import sync
from ludwig.rules.packs import load_pack

PACK = Path(__file__).resolve().parent.parent / "packs" / "joinery-nl"


def release(tmp_path, version, extra_limit=False):
    folder = tmp_path / f"release-{version}" / "joinery-nl"
    if folder.exists():
        return folder.parent
    shutil.copytree(PACK, folder)
    meta = folder / "pack.yaml"
    meta.write_text(meta.read_text().replace("version: 0.2.0", f"version: {version}"))
    if extra_limit:
        lim = folder / "limits.yaml"
        lim.write_text(lim.read_text() + "  depth_tolerance_mm: 3  # new in this release\n")
    return folder.parent


def values(folder):
    return {x.path: x.value for x in limits.read(load_pack(folder))}


def test_install_then_upgrade_keeps_factory_limits(tmp_path):
    working = tmp_path / "packs"
    assert sync(release(tmp_path, "0.2.0"), working) == ["joinery-nl 0.2.0: installed"]
    limits.update(load_pack(working / "joinery-nl"), {"reconcile.width_tolerance_mm": 3})
    assert sync(release(tmp_path, "0.2.0"), working) == []  # same version: untouched

    report = sync(release(tmp_path, "0.3.0", extra_limit=True), working)
    assert report[0].startswith("joinery-nl 0.2.0 -> 0.3.0: 1 factory limits kept")
    assert "new limits at release values: reconcile.depth_tolerance_mm" in report[0]
    got = values(working / "joinery-nl")
    assert got["reconcile.width_tolerance_mm"] == 3
    assert got["reconcile.depth_tolerance_mm"] == 3
    assert load_pack(working / "joinery-nl").version == "0.3.0"
    assert (working / ".backup" / "joinery-nl-0.2.0" / "pack.yaml").is_file()
    assert [p.parent.name for p in working.glob("*/pack.yaml")] == ["joinery-nl"]
    # The comment beside a kept value survives.
    text = (working / "joinery-nl" / "limits.yaml").read_text()
    assert "drawings and production may differ" in text


def test_command_line(tmp_path, capsys):
    assert cli.main(["packs", str(release(tmp_path, "0.2.0")), str(tmp_path / "w")]) == 0
    assert "installed" in capsys.readouterr().out
