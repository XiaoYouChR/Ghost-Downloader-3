"""Qt-free snapshot contracts for Feature Pack V1."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class StageSnapshot:
    """Stable projection of a single task stage for UI and tests."""

    id: str
    kind: str
    name: str
    state: str
    progress: float
    doneBytes: int
    speed: int
    error: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskSnapshot:
    """Stable projection of a task workflow for UI and tests."""

    id: str
    packId: str
    kind: str
    name: str
    state: str
    progress: float
    doneBytes: int
    totalBytes: int
    canPause: bool
    target: str
    stages: tuple[StageSnapshot, ...] = ()


__all__ = ["StageSnapshot", "TaskSnapshot"]
