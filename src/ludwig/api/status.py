"""Instance status for admins (PLAN 6.11): version, packs, last backup, free disk, warnings."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

BACKUP_LATE_HOURS = 26  # a daily backup plus slack
DISK_LOW_FRACTION, DISK_LOW_GB = 0.10, 2.0


def _newest_backup(folder: Path) -> float | None:
    times = [p.stat().st_mtime for p in folder.glob("db-*.dump") if p.is_file()]
    return max(times) if times else None


def report(version: str, packs: list[dict[str, str]], storage_dir: Path,
           backup_dir: Path | None, retention_days: int | None,
           counts: dict[str, int]) -> dict[str, Any]:  # fmt: skip
    """Everything an admin should see at a glance, with warnings for what needs action."""
    warnings: list[str] = []
    backup: dict[str, Any] | None = None
    if backup_dir is not None:
        newest = _newest_backup(backup_dir) if backup_dir.is_dir() else None
        if newest is None:
            warnings.append("no backup found yet")
            backup = {"newest": None, "age_hours": None}
        else:
            age = (time.time() - newest) / 3600
            backup = {"newest": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(newest)),
                      "age_hours": round(age, 1)}  # fmt: skip
            if age > BACKUP_LATE_HOURS:
                warnings.append(f"the newest backup is {age:.0f} hours old")
    storage_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(storage_dir)
    free_gb, total_gb = usage.free / 1e9, usage.total / 1e9
    if usage.free < usage.total * DISK_LOW_FRACTION or free_gb < DISK_LOW_GB:
        warnings.append(f"disk nearly full: {free_gb:.1f} GB free of {total_gb:.0f} GB")
    return {"version": version, "packs": packs, "backup": backup,
            "disk": {"free_gb": round(free_gb, 1), "total_gb": round(total_gb, 1)},
            "retention_days": retention_days, "counts": counts,
            "warnings": warnings}  # fmt: skip
