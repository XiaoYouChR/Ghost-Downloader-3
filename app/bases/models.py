import asyncio
from dataclasses import dataclass, field, fields as dataclass_fields, is_dataclass
from enum import auto, IntEnum
from pathlib import Path
from time import time_ns
from typing import ClassVar, Dict, Type, Any, TYPE_CHECKING, Iterable
from uuid import uuid4

from PySide6.QtCore import QCoreApplication
from loguru import logger
from orjson import loads, dumps
from qfluentwidgets import SettingCard

from app.supports.config import cfg, ConfigItem
from app.supports.utils import removePath, toSafeFilename


if TYPE_CHECKING:
    from app.bases.interfaces import Worker
    from app.view.pages.setting_page import SettingPage
    from PySide6.QtWidgets import QWidget


class TaskStatus(IntEnum):
    WAITING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()


class SpecialFileSize(IntEnum):
    NOT_SUPPORTED = -1
    UNKNOWN = 0


def _toSerializable(obj: Any) -> Any:
    if isinstance(obj, TaskStatus):
        return obj.name
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (TaskStage, Task)):
        result = {
            f.name: _toSerializable(getattr(obj, f.name))
            for f in dataclass_fields(obj) if f.repr
        }
        baseName = "TaskStage" if isinstance(obj, TaskStage) else "Task"
        if type(obj).__name__ != baseName:
            result["type"] = type(obj).__name__
        return result
    if is_dataclass(obj):
        return {
            f.name: _toSerializable(getattr(obj, f.name))
            for f in dataclass_fields(obj) if f.repr
        }
    if isinstance(obj, list):
        return [_toSerializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _toSerializable(v) for k, v in obj.items()}
    return obj


def _filterProperty(cls: type, obj: dict[str, Any]) -> dict[str, Any]:
    allowed = {field.name for field in dataclass_fields(cls) if field.init}
    for klass in cls.__mro__:
        for name, val in vars(klass).items():
            if isinstance(val, property):
                allowed.discard(name)
    return {key: value for key, value in obj.items() if key in allowed}


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

    def cleanup(self):
        """Remove per-stage temporary artifacts. Subclasses override."""
        pass

    @classmethod
    def fromFile(cls, file: TaskFile, task: "Task") -> "TaskStage":
        raise NotImplementedError

    def serialize(self) -> bytes:
        return dumps(_toSerializable(self))

    @classmethod
    def deserialize(cls, data: Any) -> "TaskStage":
        if isinstance(data, (bytes, bytearray, str)):
            obj = loads(data)
        else:
            obj = data

        typeName = obj.pop("type", None)
        stageCls = TaskStage._registry.get(typeName, cls) if isinstance(typeName, str) else cls

        if "status" in obj and isinstance(obj["status"], str):
            obj["status"] = TaskStatus[obj["status"]]
        if "path" in obj and isinstance(obj["path"], str):
            obj["path"] = Path(obj["path"])

        return stageCls(**_filterProperty(stageCls, obj))


@dataclass(kw_only=True, eq=False)
class Task:
    _registry: ClassVar[Dict[str, Type["Task"]]] = {}
    supportsEdit: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Task._registry[cls.__name__] = cls

    title: str
    url: str
    packId: str
    taskId: str = field(default_factory=lambda: f"tsk_{uuid4().hex}")
    status: TaskStatus = TaskStatus.WAITING
    stages: list[TaskStage] = field(default_factory=list)
    createdAt: int = field(default_factory=lambda: int(time_ns()))
    path: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))
    fileSize: int = 0
    files: list[TaskFile] | None = None
    category: str = ""
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

    def __post_init__(self):
        self.title = toSafeFilename(self.title, fallback="download")
        for stage in self.stages:
            stage._bindTask(self)
        self.updateStatus()

        if not self.category:
            from app.services.category_service import categoryService

            self.category = categoryService.categoryOf(self)

    def setTitle(self, title: str):
        self.title = toSafeFilename(title, fallback=self.title or "download")

    def currentSnapshot(self) -> tuple[float, int, int]:
        if not self.stages:
            return 0.0, 0, 0

        progress = 0.0
        speed = 0
        receivedBytes = 0
        for stage in self.stages:
            progress += stage.progress
            speed += stage.speed
            receivedBytes += stage.receivedBytes

        return progress / len(self.stages), speed, receivedBytes

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
            yield stage

    def setSelection(self, selectedIndexes: list[int]):
        if self.files is None or self.stageType is None:
            return

        selectedSet = set(selectedIndexes)

        for file in self.files:
            file.selected = file.index in selectedSet

        stagesToRemove = [
            stage for stage in self.stages
            if (fileIndex := getattr(stage, "fileIndex", None)) is not None
            and fileIndex not in selectedSet
        ]
        for stage in stagesToRemove:
            self.stages.remove(stage)

        existingFileIndexes = {
            fileIndex
            for stage in self.stages
            if (fileIndex := getattr(stage, "fileIndex", None)) is not None
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

        if "category" in payload:
            self.category = payload["category"]

    def editorCards(self, parent):
        return []

    def editorSchema(self) -> list[dict]:
        # 数据驱动编辑卡 schema（cfg/QML-free）：子类吐一串 {kind,label,field,value}，gui 通用渲染器据此渲染。
        # 替代 editorCards（qfluentwidgets）——pack 留引擎侧只吐数据，QML 端 pack-agnostic。默认不支持编辑。
        return []

    def tryKeepProgress(self, newTask: "Task") -> bool:
        # 子类默认不支持热替换 → 调用方走 replaceWith; HttpTask 在 fileSize / stage
        # 数一致时能把新 url/headers 灌进旧 stage 保住进度, 此时返回 True
        return False

    def replaceWith(self, newTask: "Task") -> None:
        # taskId / path / category 留, 其余 (url / title / fileSize / stages) 全换
        self.cleanup()
        self.url = newTask.url
        self.title = newTask.title
        self.fileSize = newTask.fileSize
        self.stages = newTask.stages
        for stage in self.stages:
            stage._bindTask(self)
        self.updateStatus()

    def cleanup(self):
        for stage in self.stages:
            stage.cleanup()

        targets: set[Path] = set()
        if self.outputFolder:
            targets.add(Path(self.outputFolder))
        for stage in self.stages:
            outputFile = getattr(stage, "outputFile", None)
            if outputFile:
                targets.add(Path(outputFile))

        for target in targets:
            removePath(target)
            removePath(Path(str(target) + ".ghd"))

    async def run(self):
        currentStage = None
        try:
            for stage in self.pendingStages():
                currentStage = stage
                worker = stage.workerType(stage)
                await worker.run()
        except asyncio.CancelledError:
            logger.info("{} stopped", self.title)
            raise
        except Exception as e:
            if currentStage is not None and not currentStage.error:
                currentStage.setError(e)
            logger.opt(exception=e).error("{} failed", self.title)
            raise

    def serialize(self) -> bytes:
        return dumps(_toSerializable(self))

    @classmethod
    def deserialize(cls, data: Any) -> "Task":
        if isinstance(data, (bytes, bytearray, str)):
            obj = loads(data)
        else:
            obj = data

        typeName = obj.pop("type", None)
        targetCls = Task._registry.get(typeName, cls) if isinstance(typeName, str) else cls

        if "status" in obj and isinstance(obj["status"], str):
            obj["status"] = TaskStatus[obj["status"]]
        if "path" in obj and isinstance(obj["path"], str):
            obj["path"] = Path(obj["path"])

        rawStages = obj.pop("stages", [])
        obj["stages"] = [TaskStage.deserialize(raw) for raw in rawStages]

        rawFiles = obj.pop("files", None)
        if rawFiles is not None and targetCls is cls:
            obj["files"] = [TaskFile(**_filterProperty(TaskFile, f)) for f in rawFiles]
        elif rawFiles is not None:
            obj["files"] = rawFiles

        return targetCls(**_filterProperty(targetCls, obj))

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

    settingsTitle: str = ""  # QML 设置页里这组的标题（如「GitHub 加速」）；空则该 pack 不出设置区

    def settingsSchema(self) -> list[dict]:
        # 数据驱动 pack 设置（替代 setupSettings 的 QtWidgets 卡）：吐 [{kind,label,key,value,options/min/max}]，
        # QML 通用渲染器据此画 SpinBox/ComboBox/Switch/…。pack 留引擎侧只吐数据，不碰 QML。默认无设置。
        return []

    def applySetting(self, key: str, value) -> None:
        # 按 key 把值写回对应 ConfigItem（key 即类属性名）。引擎收到 setPackSetting 命令时调，pack 下次读 cfg 即新值。
        item = getattr(self, key, None)
        if isinstance(item, ConfigItem):
            cfg.set(item, value)

    def dialogCards(self, parent: "QWidget") -> Iterable["SettingCard"]:
        return []

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)
