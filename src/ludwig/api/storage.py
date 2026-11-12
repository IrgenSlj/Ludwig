"""File storage keyed by content hash, plus one folder of reports per run."""

from __future__ import annotations

import hashlib
from pathlib import Path


class Storage:
    """Objects under objects/ab/<sha256>; reports under runs/<id>/."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def put(self, data: bytes) -> str:
        """Store bytes once; returns their sha256."""
        digest = hashlib.sha256(data).hexdigest()
        path = self.object(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(path)
        return digest

    def object(self, digest: str) -> Path:
        """Where an object lives."""
        return self.root / "objects" / digest[:2] / digest

    def run_dir(self, run_id: int) -> Path:
        """The report folder of a run."""
        return self.root / "runs" / str(run_id)
