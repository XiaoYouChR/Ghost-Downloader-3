"""Runtime helper values shared by Feature Pack V1 tasks and host UI."""

from __future__ import annotations

from enum import IntEnum
from enum import auto


class TaskStatus(IntEnum):
    """Download task lifecycle states used by host cards and migrated packs."""

    WAITING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()


class SpecialFileSize(IntEnum):
    """Sentinel values for tasks whose size cannot be represented as bytes yet."""

    NOT_SUPPORTED = -1
    UNKNOWN = 0


__all__ = ["SpecialFileSize", "TaskStatus"]
