from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4
import time


class TaskStatus(Enum):
    """
    Enumeration for the lifecycle status of an individual TaskStage.
    """

    WAITING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class TaskStage:
    """Represents a single, executable stage within a parent Task."""

    taskId: str
    stageIndex: int
    displayIntent: str
    workerType: str
    stageId: str = field(default_factory=lambda: f"stg_{uuid4().hex}")
    instructionPayload: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.WAITING
    progress: float = 0.0

    def __post_init__(self) -> None:
        """Validate progress is between 0 and 1."""
        if not (0 <= self.progress <= 1):
            raise ValueError(f"progress must be between 0 and 1, got {self.progress}")


@dataclass
class Task:
    """Represents a logical, user-facing task, which is a collection of stages."""

    title: str
    taskId: str = field(default_factory=lambda: f"tsk_{uuid4().hex}")
    status: TaskStatus = TaskStatus.RUNNING
    currentStageId: Optional[str] = None
    createdAt: int = field(default_factory=lambda: int(time.time()))
    metadata: dict[str, Any] = field(default_factory=dict)
