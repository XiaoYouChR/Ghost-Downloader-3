from dataclasses import dataclass, field
from enum import auto, IntEnum
from pathlib import Path
from time import time_ns
from typing import Any, Self
from uuid import uuid4

from app.supports.config import cfg


class TaskStatus(IntEnum):
    """
    Enumeration for the lifecycle status of an individual TaskStage.
    """

    WAITING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass(kw_only=True)
class TaskStage:
    """Represents a single, executable stage within a parent Task."""

    stageIndex: int
    stageId: str = field(default_factory=lambda: f"stg_{uuid4().hex}")
    # metadata: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.WAITING
    progress: float = 0   # 0 ~ 100
    speed: int = field(default=1)

    def __post_init__(self) -> None:
        """Validate progress is between 0 and 1."""
        if not (0 <= self.progress <= 1):
            raise ValueError(f"progress must be between 0 and 1, got {self.progress}")

    def serialize(self) -> dict[str, Any]:
        raise NotImplementedError

    def deserialize(self, dict: dict[str, Any]) -> Self:
        raise NotImplementedError


@dataclass(kw_only=True)
class Task:
    """Represents a logical, user-facing task, which is a collection of stages."""

    title: str
    taskId: str = field(default_factory=lambda: f"tsk_{uuid4().hex}")
    status: TaskStatus = TaskStatus.RUNNING
    stages: list[TaskStage] = field(default_factory=list)
    createdAt: int = field(default_factory=lambda: int(time_ns()))
    path: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))

    def serialize(self) -> dict[str, Any]:
        raise NotImplementedError

    def deserialize(self, dict: dict[str, Any]) -> Self:
        raise NotImplementedError

    async def run(self):
        self.stages.sort(key=lambda stage: stage.stageIndex)
        raise NotImplementedError

    def __hash__(self):
        return hash(self.taskId)
