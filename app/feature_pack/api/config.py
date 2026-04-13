"""Public ``TaskConfig`` contract for Feature Pack V1."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskConfig:
    """Stable task configuration submitted through ``Task.configure()``."""

    source: str
    folder: Path
    name: str
    headers: dict[str, str] = field(default_factory=dict)
    proxies: dict[str, str] | None = None
    chunks: int = 1


__all__ = ["TaskConfig"]
