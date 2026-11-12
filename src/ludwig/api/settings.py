"""Service settings, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Where the service keeps its data and which packs it offers."""

    database_url: str = "sqlite:///./ludwig.db"
    storage_dir: Path = Path("storage")
    packs_dir: Path = Path("packs")
    api_token: str | None = None
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)
    max_upload_mb: int = 200
    web_dir: Path | None = None

    @classmethod
    def from_env(cls) -> Settings:
        """LUDWIG_DATABASE_URL, LUDWIG_STORAGE_DIR, LUDWIG_PACKS_DIR, LUDWIG_API_TOKEN,
        LUDWIG_ALLOWED_ORIGINS (comma separated), LUDWIG_MAX_UPLOAD_MB, LUDWIG_WEB_DIR."""
        env = os.environ
        raw = env.get("LUDWIG_ALLOWED_ORIGINS", "")
        origins = tuple(o.strip() for o in raw.split(",") if o.strip())
        return cls(
            database_url=env.get("LUDWIG_DATABASE_URL", cls.database_url),
            storage_dir=Path(env.get("LUDWIG_STORAGE_DIR", "storage")),
            packs_dir=Path(env.get("LUDWIG_PACKS_DIR", "packs")),
            api_token=env.get("LUDWIG_API_TOKEN") or None,
            allowed_origins=origins,
            max_upload_mb=int(env.get("LUDWIG_MAX_UPLOAD_MB", "200")),
            web_dir=Path(env["LUDWIG_WEB_DIR"]) if env.get("LUDWIG_WEB_DIR") else None,
        )
