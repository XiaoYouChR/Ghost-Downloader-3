from dataclasses import asdict, dataclass, field, fields as dataclass_fields, is_dataclass
from enum import auto, IntEnum
from pathlib import Path
from time import time_ns
from typing import ClassVar, Dict, Type, Any, TYPE_CHECKING, Iterable
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


def _filterDataclassKwargs(cls: type, obj: dict[str, Any]) -> dict[str, Any]:
    allowed = {field.name for field in dataclass_fields(cls) if field.init}
    return {key: value for key, value in obj.items() if key in allowed}


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
    receivedBytes: int = field(default=0)
    speed: int = field(default=1)   # division cannot be 0
    error: str = field(default="")

    def bindTask(self, task: "Task"):
        self._task = task

    def setStatus(self, status: TaskStatus, notifyTask: bool = True):
        self.status = status
        if status == TaskStatus.COMPLETED:
            self.progress = 100
            self.speed = 0
            self.error = ""
        elif status in {TaskStatus.WAITING, TaskStatus.PAUSED}:
            self.speed = 0
            self.error = ""
        elif status == TaskStatus.FAILED:
            self.speed = 0

        if notifyTask and hasattr(self, "_task"):
            self._task.syncStatusFromStages()

    def setError(self, error: Any, notifyTask: bool = True):
        message = repr(error).strip() if error is not None else ""
        self.error = message
        self.setStatus(TaskStatus.FAILED, notifyTask=notifyTask)

    def reset(self, notifyTask: bool = True):
        self.status = TaskStatus.WAITING
        self.progress = 0
        self.receivedBytes = 0
        self.speed = 0
        self.error = ""

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

        return stageCls(**_filterDataclassKwargs(stageCls, obj))


@dataclass(kw_only=True)
class Task:
    """Represents a logical, user-facing task, which is a collection of stages."""

    title: str
    url: str
    taskId: str = field(default_factory=lambda: f"tsk_{uuid4().hex}")
    status: TaskStatus = TaskStatus.WAITING
    stages: list[TaskStage] = field(default_factory=list)
    createdAt: int = field(default_factory=lambda: int(time_ns()))
    path: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))
    fileSize: int

    @property
    def resolvePath(self) -> str:
        return str(self.path / self.title)

    def setTitle(self, title: str):
        self.title = title
        self.syncStagePaths()

    def syncStagePaths(self):
        raise NotImplementedError

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
            if status == TaskStatus.RUNNING and stage.status == TaskStatus.FAILED:
                stage.reset(notifyTask=False)
            stage.setStatus(status, notifyTask=False)

        return self.syncStatusFromStages()

    def reset(self) -> TaskStatus:
        if not self.stages:
            self.status = TaskStatus.WAITING
            return self.status

        for stage in self.stages:
            stage.reset(notifyTask=False)

        return self.syncStatusFromStages()

    @property
    def lastError(self) -> str:
        for stage in reversed(self.stages):
            if stage.status == TaskStatus.FAILED and stage.error:
                return stage.error

        for stage in reversed(self.stages):
            if stage.error:
                return stage.error

        return ""

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

        return targetCls(**_filterDataclassKwargs(targetCls, obj))

    def applyPayloadToTask(self, payload: dict[str, Any]):
        path = payload.get("path")
        if isinstance(path, (str, Path)):
            self.path = Path(path)

    def canPause(self) -> bool:
        return True

    def occupiesDownloadSlot(self) -> bool:
        return self.status == TaskStatus.RUNNING

    def willOccupyDownloadSlotWhenStarted(self) -> bool:
        return True

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
                setattr(cfg.__class__, f"pack_{cls.__name__}_{attr_name}", attr_value)

        cfg.load()

    def loadSettingCards(self, settingPage: "SettingPage"):
        """加载设置界面上的设置卡片，子类可重写此方法以添加自定义的设置卡片"""
        raise NotImplementedError

    def getDialogCards(self, parent: "QWidget") -> Iterable["SettingCard"]:
        """在解析时往解析窗口加入设置卡片"""
        return []

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)


class SpecialFileSize(IntEnum):
    NOT_SUPPORTED = -1
    UNKNOWN = 0
