from dataclasses import asdict, dataclass, field, is_dataclass

from typing import ClassVar, Dict, Type, Any
from enum import auto, IntEnum
from pathlib import Path
from time import time_ns
from uuid import uuid4

from orjson import loads, dumps

from app.supports.config import cfg


def _toSerializable(obj: Any) -> Any:
    if isinstance(obj, TaskStatus):
        return obj.name
    if isinstance(obj, Path):
        return str(obj)
    if is_dataclass(obj):
        result: dict[str, Any] = {}
        for key, value in asdict(obj).items():
            result[key] = _toSerializable(value)
        return result
    if isinstance(obj, list):
        return [_toSerializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _toSerializable(v) for k, v in obj.items()}
    return obj


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

    _registry: ClassVar[Dict[str, Type["TaskStage"]]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        TaskStage._registry[cls.__name__] = cls

    stageIndex: int
    stageId: str = field(default_factory=lambda: f"stg_{uuid4().hex}")
    status: TaskStatus = TaskStatus.WAITING
    progress: float = 0   # 0 ~ 100
    speed: int = field(default=1)

    def serialize(self) -> bytes:
        obj = _toSerializable(self)
        if type(self).__name__ != "TaskStage":
            obj["type"] = type(self).__name__
        return dumps(obj)

    @classmethod
    def deserialize(cls, data: Any) -> "TaskStage":
        if isinstance(data, (bytes, bytearray, str)):
            obj = loads(data)
        else:
            obj = data

        if "type" in obj and isinstance(obj["type"], str):
            stageCls = TaskStage._registry.get(obj["type"], cls)
            obj.pop("type", None)
        else:
            stageCls = cls

        if "status" in obj and isinstance(obj["status"], str):
            obj["status"] = TaskStatus[obj["status"]]
        if "path" in obj and isinstance(obj["path"], str):
            obj["path"] = Path(obj["path"])

        return stageCls(**obj)


@dataclass(kw_only=True)
class Task:
    """Represents a logical, user-facing task, which is a collection of stages."""

    title: str
    taskId: str = field(default_factory=lambda: f"tsk_{uuid4().hex}")
    status: TaskStatus = TaskStatus.RUNNING
    stages: list[TaskStage] = field(default_factory=list)
    createdAt: int = field(default_factory=lambda: int(time_ns()))
    path: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))

    def serialize(self) -> bytes:
        obj = _toSerializable(self)
        if type(self).__name__ != "Task":
            obj["type"] = type(self).__name__
        if "stages" in obj:
            obj["stages"] = [loads(stage.serialize()) for stage in self.stages]
        return dumps(obj)

    _registry: ClassVar[Dict[str, Type["Task"]]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Task._registry[cls.__name__] = cls

    @classmethod
    def deserialize(cls, data: Any) -> "Task":
        if isinstance(data, (bytes, bytearray, str)):
            obj = loads(data)
        else:
            obj = data

        targetCls: Type[Task] = cls
        if "type" in obj and isinstance(obj["type"], str):
            targetCls = Task._registry.get(obj["type"], cls)
            obj.pop("type", None)

        if "status" in obj and isinstance(obj["status"], str):
            obj["status"] = TaskStatus[obj["status"]]
        if "path" in obj and isinstance(obj["path"], str):
            obj["path"] = Path(obj["path"])

        rawStages = obj.get("stages", [])
        stages: list = []
        for raw in rawStages:
            stages.append(TaskStage.deserialize(raw))
        obj["stages"] = stages

        return targetCls(**obj)

    async def run(self):
        self.stages.sort(key=lambda stage: stage.stageIndex)
        raise NotImplementedError

    def __hash__(self):
        return hash(self.taskId)
