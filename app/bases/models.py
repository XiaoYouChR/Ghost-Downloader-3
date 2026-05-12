import asyncio
from dataclasses import asdict, dataclass, field, fields as dataclass_fields, is_dataclass
from enum import auto, IntEnum
from pathlib import Path
from time import time_ns
from typing import ClassVar, Dict, Type, Any, TYPE_CHECKING, Iterable
from uuid import uuid4

from loguru import logger
from PySide6.QtCore import QCoreApplication
from orjson import loads, dumps
from qfluentwidgets import SettingCard

from app.supports.config import cfg, ConfigItem
from app.supports.utils import sanitizeFilename

if TYPE_CHECKING:
    from app.bases.interfaces import Worker
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
    WAITING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass(kw_only=True)
class TaskFile:
    index: int
    relativePath: str
    size: int = 0
    selected: bool = True
    downloadedBytes: int = 0
    completed: bool = False


@dataclass(kw_only=True)
class TaskStage:
    _registry: ClassVar[Dict[str, Type["TaskStage"]]] = {}
    workerType: ClassVar[Type["Worker"]]
    canPause: ClassVar[bool] = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        TaskStage._registry[cls.__name__] = cls

    stageIndex: int
    stageId: str = field(default_factory=lambda: f"stg_{uuid4().hex}")
    status: TaskStatus = TaskStatus.WAITING
    progress: float = 0
    receivedBytes: int = 0
    speed: int = 0
    error: str = ""

    def _bindTask(self, task: "Task"):
        self._task = task

    @property
    def task(self) -> "Task":
        return self._task

    def setStatus(self, status: TaskStatus, sync: bool = True):
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

        if sync and hasattr(self, "_task"):
            self._task.updateStatus()

    def setError(self, error: Any, sync: bool = True):
        message = repr(error).strip() if error is not None else ""
        self.error = message
        self.setStatus(TaskStatus.FAILED, sync=sync)

    def reset(self, sync: bool = True):
        self.status = TaskStatus.WAITING
        self.progress = 0
        self.receivedBytes = 0
        self.speed = 0
        self.error = ""

        if sync and hasattr(self, "_task"):
            self._task.updateStatus()

    def updateOutputFile(self, taskPath: Path, taskTitle: str):
        pass

    def onCompleted(self, task: "Task"):
        pass

    @classmethod
    def fromFile(cls, file: TaskFile, task: "Task") -> "TaskStage":
        raise NotImplementedError

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
    title: str
    url: str
    packId: str
    taskId: str = field(default_factory=lambda: f"tsk_{uuid4().hex}")
    status: TaskStatus = TaskStatus.WAITING
    stages: list[TaskStage] = field(default_factory=list)
    createdAt: int = field(default_factory=lambda: int(time_ns()))
    path: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))
    fileSize: int = 0
    metadata: dict = field(default_factory=dict)
    files: list[TaskFile] | None = None
    usesSlot: bool = True
    stageType: Type[TaskStage] | None = field(default=None, repr=False)

    @property
    def outputFolder(self) -> str:
        return str(self.path / self.title)

    @property
    def canPause(self) -> bool:
        for stage in self.stages:
            if stage.status == TaskStatus.RUNNING:
                return stage.canPause
        return True

    @property
    def lastError(self) -> str:
        for stage in reversed(self.stages):
            if stage.status == TaskStatus.FAILED and stage.error:
                return stage.error
        for stage in reversed(self.stages):
            if stage.error:
                return stage.error
        return ""

    def setTitle(self, title: str):
        self.title = sanitizeFilename(title, fallback=self.title or "download")
        for stage in self.stages:
            stage.updateOutputFile(self.path, self.title)

    def __post_init__(self):
        self.title = sanitizeFilename(self.title, fallback="download")
        for stage in self.stages:
            stage._bindTask(self)
        for stage in self.stages:
            stage.updateOutputFile(self.path, self.title)
        self.updateStatus()

    def addStage(self, stage: TaskStage):
        stage._bindTask(self)
        self.stages.append(stage)
        self.updateStatus()

    def removeStage(self, stage: TaskStage):
        self.stages.remove(stage)
        self.updateStatus()

    def updateStatus(self) -> TaskStatus:
        if not self.stages:
            return self.status

        statuses = [stage.status for stage in self.stages]
        if any(s == TaskStatus.FAILED for s in statuses):
            self.status = TaskStatus.FAILED
        elif all(s == TaskStatus.COMPLETED for s in statuses):
            self.status = TaskStatus.COMPLETED
        elif any(s == TaskStatus.RUNNING for s in statuses):
            self.status = TaskStatus.RUNNING
        elif all(s == TaskStatus.PAUSED for s in statuses):
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
                stage.reset(sync=False)
            stage.setStatus(status, sync=False)

        return self.updateStatus()

    def reset(self) -> TaskStatus:
        if not self.stages:
            self.status = TaskStatus.WAITING
            return self.status

        for stage in self.stages:
            stage.reset(sync=False)

        return self.updateStatus()

    def pendingStages(self) -> Iterable[TaskStage]:
        self.stages.sort(key=lambda stage: stage.stageIndex)
        for stage in self.stages:
            if self.status != TaskStatus.RUNNING:
                break
            if stage.status == TaskStatus.COMPLETED:
                continue
            self._onStageStarted(stage)
            yield stage

    def _onStageStarted(self, stage: TaskStage):
        from app.supports.recorder import taskRecorder
        taskRecorder.flush()

    def setSelection(self, selectedIndexes: list[int]):
        if self.files is None or self.stageType is None:
            return

        selectedSet = set(selectedIndexes)

        for file in self.files:
            file.selected = file.index in selectedSet

        stagesToRemove = [
            stage for stage in self.stages
            if hasattr(stage, "fileIndex") and stage.fileIndex not in selectedSet
        ]
        for stage in stagesToRemove:
            self.stages.remove(stage)

        existingFileIndexes = {
            stage.fileIndex for stage in self.stages
            if hasattr(stage, "fileIndex")
        }
        for file in self.files:
            if file.selected and file.index not in existingFileIndexes:
                newStage = self.stageType.fromFile(file, self)
                self.addStage(newStage)

        self.fileSize = sum(f.size for f in self.files if f.selected)
        self.updateStatus()

    def applySettings(self, payload: dict):
        path = payload.get("path")
        if isinstance(path, (str, Path)):
            self.path = Path(path)
            for stage in self.stages:
                stage.updateOutputFile(self.path, self.title)

    async def run(self):
        currentStage = None
        try:
            for stage in self.pendingStages():
                currentStage = stage
                worker = stage.workerType(stage)
                await worker.run()
                stage.onCompleted(self)
        except asyncio.CancelledError:
            logger.info("{} stopped", self.title)
            raise
        except Exception as e:
            if currentStage is not None and not currentStage.error:
                currentStage.setError(e)
            logger.opt(exception=e).error("{} failed", self.title)
            raise

    def serialize(self) -> bytes:
        obj = _toSerializable(self)
        obj.pop("stageType", None)
        if "stages" in obj:
            obj["stages"] = [loads(stage.serialize()) for stage in self.stages]
        if "files" in obj and self.files is not None:
            obj["files"] = [_toSerializable(f) for f in self.files]
        return dumps(obj)

    @classmethod
    def deserialize(cls, data: Any) -> "Task":
        if isinstance(data, (bytes, bytearray, str)):
            obj = loads(data)
        else:
            obj = data

        obj.pop("type", None)

        if "status" in obj and isinstance(obj["status"], str):
            obj["status"] = TaskStatus[obj["status"]]
        if "path" in obj and isinstance(obj["path"], str):
            obj["path"] = Path(obj["path"])

        rawStages = obj.pop("stages", [])
        stages = [TaskStage.deserialize(raw) for raw in rawStages]
        obj["stages"] = stages

        rawFiles = obj.pop("files", None)
        if rawFiles is not None:
            obj["files"] = [TaskFile(**_filterDataclassKwargs(TaskFile, f)) for f in rawFiles]

        return cls(**_filterDataclassKwargs(cls, obj))

    def __hash__(self):
        return hash(self.taskId)


class PackConfig:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        for attr_name, attr_value in cls.__dict__.items():
            if isinstance(attr_value, ConfigItem):
                setattr(cfg.__class__, f"pack_{cls.__name__}_{attr_name}", attr_value)

        cfg.load()

    def setupSettings(self, settingPage: "SettingPage"):
        raise NotImplementedError

    def dialogCards(self, parent: "QWidget") -> Iterable["SettingCard"]:
        return []

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)


class SpecialFileSize(IntEnum):
    NOT_SUPPORTED = -1
    UNKNOWN = 0
