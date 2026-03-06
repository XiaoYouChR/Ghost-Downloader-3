from dataclasses import asdict, dataclass, field, is_dataclass

from typing import ClassVar, Dict, Type, Any, TYPE_CHECKING, Iterable
from enum import auto, IntEnum
from pathlib import Path
from time import time_ns
from uuid import uuid4

from PySide6.QtCore import QCoreApplication
from orjson import loads, dumps
from qfluentwidgets import SettingCard

from app.supports.config import cfg, ConfigItem

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage
    from PySide6.QtWidgets import QWidget

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
    speed: int = field(default=1)   # division cannot be 0

    def bindTask(self, task: "Task"):
        self._task = task

    def setStatus(self, status: TaskStatus, notifyTask: bool = True):
        self.status = status
        if status == TaskStatus.COMPLETED:
            self.progress = 100
            self.speed = 0
        elif status in {TaskStatus.WAITING, TaskStatus.PAUSED, TaskStatus.FAILED}:
            self.speed = 0

        if notifyTask and hasattr(self, "_task"):
            self._task.syncStatusFromStages()

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
    status: TaskStatus = TaskStatus.WAITING
    stages: list[TaskStage] = field(default_factory=list)
    createdAt: int = field(default_factory=lambda: int(time_ns()))
    path: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))

    @property
    def resolvePath(self) -> str:
        return str(self.path / self.title)

    def __post_init__(self):
        for stage in self.stages:
            stage.bindTask(self)
        self.syncStatusFromStages()

    def addStage(self, stage: TaskStage):
        stage.bindTask(self)
        self.stages.append(stage)
        self.syncStatusFromStages()

    def syncStatusFromStages(self) -> TaskStatus:
        if not self.stages:
            return self.status

        stageStatus = [stage.status for stage in self.stages]
        if any(status == TaskStatus.FAILED for status in stageStatus):
            self.status = TaskStatus.FAILED
        elif all(status == TaskStatus.COMPLETED for status in stageStatus):
            self.status = TaskStatus.COMPLETED
        elif any(status == TaskStatus.RUNNING for status in stageStatus):
            self.status = TaskStatus.RUNNING
        elif all(status == TaskStatus.PAUSED for status in stageStatus):
            self.status = TaskStatus.PAUSED
        else:
            self.status = TaskStatus.WAITING

        return self.status

    def setStatus(self, status: TaskStatus) -> TaskStatus:
        if not self.stages:
            self.status = status
            return self.status

        for stage in self.stages:
            if stage.status == TaskStatus.COMPLETED:
                continue
            stage.setStatus(status, notifyTask=False)

        return self.syncStatusFromStages()

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

    def applyPayloadToTask(self, payload: dict[str, Any]):
        path = payload.get("path")
        if isinstance(path, (str, Path)):
            self.path = Path(path)

    async def run(self):
        self.stages.sort(key=lambda stage: stage.stageIndex)
        raise NotImplementedError

    def __hash__(self):
        return hash(self.taskId)

class PackConfig:
    def __init_subclass__(cls, **kwargs):
        """将子类的所有 ConfigItem 成员添加到 cfg 中，并使用 cfg.load 重新加载配置文件"""
        super().__init_subclass__(**kwargs)

        for attr_name, attr_value in cls.__dict__.items():
            if isinstance(attr_value, ConfigItem):
                setattr(cfg.__class__, attr_name, attr_value)

        cfg.load()

    def loadSettingCards(self, settingPage: "SettingPage"):
        """加载设置界面上的设置卡片，子类可重写此方法以添加自定义的设置卡片"""
        raise NotImplementedError

    def getDialogCards(self, parent: "QWidget") -> Iterable["SettingCard"]:
        """在解析时往解析窗口加入设置卡片"""
        raise NotImplementedError

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)
