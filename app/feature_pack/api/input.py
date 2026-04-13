"""Public ``TaskInput`` contract for Feature Pack V1."""

from __future__ import annotations

from dataclasses import dataclass

from .config import TaskConfig


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskInput:
    """Normalized host input passed into ``FeaturePack.createTask()``."""

    config: TaskConfig
    size: int = 0
    hints: tuple[dict[str, object], ...] = ()


__all__ = ["TaskInput"]
