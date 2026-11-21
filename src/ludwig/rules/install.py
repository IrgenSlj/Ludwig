"""Install or upgrade the packs of a hosted instance, keeping each factory's own limit values.

The image carries the packs as released; the instance keeps its working copy in a volume,
where the limits editor writes. On start, a pack missing from the volume is copied in, and
a pack whose released version differs is replaced by the release with the factory's limit
values carried over for every limit that still exists.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ludwig.rules import limits
from ludwig.rules.packs import PackError, load_pack


def sync(released: Path, working: Path) -> list[str]:
    """Bring `working` up to the packs in `released`; returns one line per change."""
    working.mkdir(parents=True, exist_ok=True)
    report = []
    for source in sorted(p.parent for p in released.glob("*/pack.yaml")):
        target = working / source.name
        new = load_pack(source)
        if not (target / "pack.yaml").is_file():
            shutil.copytree(source, target)
            report.append(f"{new.name} {new.version}: installed")
            continue
        try:
            old = load_pack(target)
        except PackError as exc:
            report.append(f"{source.name}: working copy does not load ({exc}); left as it is")
            continue
        if old.version == new.version:
            continue
        kept = {x.path: x.value for x in limits.read(old)}
        # Two levels down, so the packs scan (*/pack.yaml) never offers the old copy.
        backup = working / ".backup" / f"{target.name}-{old.version}"
        shutil.rmtree(backup, ignore_errors=True)
        backup.parent.mkdir(exist_ok=True)
        target.rename(backup)
        shutil.copytree(source, target)
        fresh = {x.path: x.value for x in limits.read(load_pack(target))}
        carried = {k: v for k, v in kept.items() if k in fresh and fresh[k] != v}
        note = ""
        if carried:
            try:
                limits.update(load_pack(target), carried)
            except ValueError as exc:
                note = f"; factory limits NOT kept, they do not fit the new rules ({exc})"
                carried = {}
        dropped = sorted(set(kept) - set(fresh))
        added = sorted(set(fresh) - set(kept))
        line = f"{new.name} {old.version} -> {new.version}: {len(carried)} factory limits kept"
        if added:
            line += f"; new limits at release values: {', '.join(added)}"
        if dropped:
            line += f"; limits no longer used: {', '.join(dropped)}"
        report.append(line + note + f"; previous copy in .backup/{backup.name}")
    return report
