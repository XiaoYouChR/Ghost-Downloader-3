from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import auto, IntEnum
from pathlib import Path
from time import time
from typing import Callable, ClassVar, Iterable, Type
from uuid import uuid4

from loguru import logger

from app.config.cfg import cfg
from app.platform.filesystem import toSafeFilename



class TaskStatus(IntEnum):
    WAITING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()


class SpecialFileSize(IntEnum):
    NOT_SUPPORTED = -1
    UNKNOWN = 0


class TaskError(Exception):
    def __init__(self, message: str, **params):
        super().__init__(message)
        self.message = message
        self.params = params

    def __str__(self) -> str:
        return self.message.format_map(self.params) if self.params else self.message


@dataclass(frozen=True)
class StepError:
    message: str
    params: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message.format_map(self.params)

    def __bool__(self) -> bool:
        return bool(self.message)


@dataclass(frozen=True)
class TaskOptions:
    url: str
    outputFolder: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))
    headers: dict[str, str] = field(
        default_factory=lambda: dict(cfg.defaultRequestHeaders.value)
    )
    clientProfile: str = ""
    userAgent: str = ""
    sourceUserAgent: str = ""
    subworkerCount: int = field(default_factory=lambda: cfg.preBlockNum.value)

    @classmethod
    def fromOptions(cls, options: dict) -> TaskOptions:
        from app.models.serialization import filterFields
        return cls(**filterFields(cls, options))


@dataclass(frozen=True)
class ResourceTaskOptions(TaskOptions):
    name: str = ""
    size: int = 0
    canUseRangeRequests: bool = False


@dataclass(frozen=True)
class PageTaskOptions(TaskOptions):
    pageUrl: str = ""
    pageTitle: str = ""


@dataclass(frozen=True)
class MergeTaskOptions(TaskOptions):
    video: ResourceTaskOptions | None = None
    audio: ResourceTaskOptions | None = None


@dataclass(frozen=True)
class BinaryInstallOptions(TaskOptions):
    name: str = ""
    executableNames: tuple[str, ...] = ()
    sha256Url: str = ""


@dataclass(kw_only=True)
class TaskFile:
    index: int
    relativePath: str
    size: int = 0
    selected: bool = True
    downloadedBytes: int = 0
    completed: bool = False


@dataclass(kw_only=True)
class TaskStep:
    _registry: ClassVar[dict[str, Type[TaskStep]]] = {}
    canPause: ClassVar[bool] = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        TaskStep._registry[cls.__name__] = cls

    stepIndex: int
    stepId: str = field(default_factory=lambda: f"stp_{uuid4().hex}")
    status: TaskStatus = TaskStatus.WAITING
    progress: float = 0
    receivedBytes: int = 0
    speed: int = 0
    error: StepError | None = field(default=None, repr=False, init=False)

    def _bindTask(self, task: Task) -> None:
        self._task = task

    @property
    def task(self) -> Task:
        return self._task

    def setStatus(self, status: TaskStatus) -> None:
        self.status = status
        if status == TaskStatus.COMPLETED:
            self.progress = 100
            self.speed = 0
            self.error = None
        elif status in {TaskStatus.WAITING, TaskStatus.PAUSED}:
            self.speed = 0
            self.error = None
        elif status == TaskStatus.FAILED:
            self.speed = 0

        if hasattr(self, "_task"):
            self._task.updateStatus()

    def setError(self, error: StepError) -> None:
        self.error = error
        self.status = TaskStatus.FAILED
        self.speed = 0
        if hasattr(self, "_task"):
            self._task.updateStatus()

    def reset(self) -> None:
        self.status = TaskStatus.WAITING
        self.progress = 0
        self.receivedBytes = 0
        self.speed = 0
        self.error = None
        if hasattr(self, "_task"):
            self._task.updateStatus()

    def setOptions(self, options: dict) -> None:
        pass

    async def run(self, reportSpeed: Callable[[int], None], waitForSpeedLimit: Callable[[], None]) -> None:
        raise NotImplementedError

    @property
    def outputPath(self) -> str:
        return ""

    def deleteFiles(self) -> None:
        pass

    def moveFiles(self, oldFolder: Path, newFolder: Path) -> None:
        from shutil import move
        rawPath = self.outputPath
        if not rawPath:
            return
        oldPath = Path(rawPath)
        if not oldPath.exists():
            return
        try:
            relPath = oldPath.relative_to(oldFolder)
        except ValueError:
            return
        newPath = newFolder / relPath
        newPath.parent.mkdir(parents=True, exist_ok=True)
        move(str(oldPath), str(newPath))
        ghdPath = Path(f"{oldPath}.ghd")
        if ghdPath.exists():
            move(str(ghdPath), str(newFolder / f"{relPath}.ghd"))

    @classmethod
    def fromFile(cls, file: TaskFile, task: Task) -> TaskStep:
        raise NotImplementedError

    def toDict(self) -> dict:
        from app.models.serialization import toDict
        return toDict(self)

    @classmethod
    def fromDict(cls, data) -> TaskStep:
        from app.models.serialization import fromDict
        return fromDict(data, cls)


@dataclass(kw_only=True, eq=False)
class Task:
    _registry: ClassVar[dict[str, Type[Task]]] = {}
    canEdit: ClassVar[bool] = False
    fileType: ClassVar[type] = TaskFile
    hasOutputFile: ClassVar[bool] = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Task._registry[cls.__name__] = cls

    name: str
    url: str
    packId: str
    taskId: str = field(default_factory=lambda: f"tsk_{uuid4().hex}")
    status: TaskStatus = TaskStatus.WAITING
    steps: list[TaskStep] = field(default_factory=list)
    createdAt: int = field(default_factory=lambda: int(time()))
    completedAt: int = 0
    outputFolder: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))
    fileSize: int = 0
    files: list[TaskFile] | None = None
    category: str | None = None

    @property
    def outputPath(self) -> str:
        return str(self.outputFolder / self.name)

    @property
    def canPause(self) -> bool:
        for step in self.steps:
            if step.status == TaskStatus.RUNNING:
                return step.canPause
        return True

    @property
    def lastError(self) -> StepError | None:
        for step in reversed(self.steps):
            if step.status == TaskStatus.FAILED and step.error:
                return step.error
        for step in reversed(self.steps):
            if step.error:
                return step.error
        return None

    def __post_init__(self) -> None:
        self.name = toSafeFilename(self.name, fallback="download")
        for step in self.steps:
            step._bindTask(self)
        self.updateStatus()

    def setName(self, name: str) -> None:
        self.name = toSafeFilename(name, fallback=self.name or "download")

    def deduplicateFilename(self) -> None:
        from app.platform.filesystem import deduplicateName
        self.name = deduplicateName(self.outputFolder, self.name)

    def setOptions(self, options: dict) -> None:
        newFolder = options.get("outputFolder")
        if isinstance(newFolder, (str, Path)):
            newFolder = Path(newFolder)
            if newFolder != self.outputFolder:
                self._move(newFolder)
        if "category" in options:
            self.category = options["category"]
        for step in self.steps:
            step.setOptions(options)

    def _move(self, newFolder: Path) -> None:
        oldFolder = self.outputFolder
        newFolder.mkdir(parents=True, exist_ok=True)
        for step in self.steps:
            step.moveFiles(oldFolder, newFolder)
        self.outputFolder = newFolder

    def _isStepSelected(self, step: TaskStep) -> bool:
        if not self.files:
            return True
        fileIndex = getattr(step, "fileIndex", None)
        if fileIndex is None:
            return True
        for file in self.files:
            if file.index == fileIndex:
                return file.selected
        return False

    def _updateFilesFromSteps(self) -> None:
        if not self.files:
            return
        received: dict[int, int] = {}
        completed: dict[int, bool] = {}
        for step in self.steps:
            fileIndex = getattr(step, "fileIndex", None)
            if fileIndex is None:
                continue
            received[fileIndex] = received.get(fileIndex, 0) + step.receivedBytes
            completed[fileIndex] = completed.get(fileIndex, True) and step.status == TaskStatus.COMPLETED
        for file in self.files:
            if file.index in received:
                file.downloadedBytes = received[file.index]
                file.completed = completed[file.index]

    def currentSnapshot(self) -> tuple[float, int, int]:
        steps = [s for s in self.steps if self._isStepSelected(s)]
        if not steps:
            return 0.0, 0, 0
        progress = 0.0
        speed = 0
        receivedBytes = 0
        for step in steps:
            progress += step.progress
            speed += step.speed
            receivedBytes += step.receivedBytes
        return progress / len(steps), speed, receivedBytes

    def updateStatus(self) -> TaskStatus:
        self._updateFilesFromSteps()
        steps = [s for s in self.steps if self._isStepSelected(s)]
        if not steps:
            return self.status
        statuses = [step.status for step in steps]
        if any(s == TaskStatus.FAILED for s in statuses):
            self.status = TaskStatus.FAILED
        elif all(s == TaskStatus.COMPLETED for s in statuses):
            self.status = TaskStatus.COMPLETED
            if not self.completedAt:
                self.completedAt = int(time())
            if self.fileSize <= 0:
                _, _, receivedBytes = self.currentSnapshot()
                if receivedBytes > 0:
                    self.fileSize = receivedBytes
        elif any(s == TaskStatus.RUNNING for s in statuses):
            self.status = TaskStatus.RUNNING
        elif all(s == TaskStatus.PAUSED for s in statuses):
            self.status = TaskStatus.PAUSED
        else:
            self.status = TaskStatus.WAITING
        return self.status

    def setStatus(self, status: TaskStatus) -> TaskStatus:
        steps = [s for s in self.steps if self._isStepSelected(s)]
        if not steps:
            self.status = status
            return self.status
        for step in steps:
            if step.status == TaskStatus.COMPLETED:
                continue
            if status == TaskStatus.RUNNING and step.status == TaskStatus.FAILED:
                step.status = TaskStatus.WAITING
                step.progress = 0
                step.receivedBytes = 0
                step.speed = 0
                step.error = None
            step.status = status
            step.speed = 0
            if status == TaskStatus.COMPLETED:
                step.progress = 100
                step.error = None
            elif status in {TaskStatus.WAITING, TaskStatus.PAUSED}:
                step.error = None
        return self.updateStatus()

    def reset(self) -> TaskStatus:
        self.completedAt = 0
        if not self.steps:
            self.status = TaskStatus.WAITING
            return self.status
        for step in self.steps:
            step.status = TaskStatus.WAITING
            step.progress = 0
            step.receivedBytes = 0
            step.speed = 0
            step.error = None
        return self.updateStatus()

    def addStep(self, step: TaskStep) -> None:
        step._bindTask(self)
        self.steps.append(step)
        self.updateStatus()

    def removeStep(self, step: TaskStep) -> None:
        self.steps.remove(step)
        self.updateStatus()

    def setSelection(self, selectedIndexes: list[int]) -> None:
        if self.files is None:
            return
        selectedSet = set(selectedIndexes)
        for file in self.files:
            file.selected = file.index in selectedSet
        self.fileSize = sum(f.size for f in self.files if f.selected)
        self.updateStatus()

    def pendingSteps(self) -> Iterable[TaskStep]:
        for step in sorted(self.steps, key=lambda step: step.stepIndex):
            if self.status != TaskStatus.RUNNING:
                break
            if not self._isStepSelected(step):
                continue
            if step.status == TaskStatus.COMPLETED:
                continue
            yield step

    def deleteFiles(self) -> None:
        from app.platform.filesystem import deletePath
        for step in self.steps:
            step.deleteFiles()
        targets: set[Path] = set()
        if self.outputPath:
            targets.add(Path(self.outputPath))
        for step in self.steps:
            outputFile = getattr(step, "outputFile", "")
            if outputFile:
                targets.add(Path(outputFile))
        for target in targets:
            deletePath(target)
            deletePath(Path(str(target) + ".ghd"))

    def canReuseProgress(self, newTask: Task) -> bool:
        return False

    def replaceWith(self, newTask: Task) -> None:
        self.url = newTask.url
        self.name = newTask.name
        self.fileSize = newTask.fileSize
        self.steps = newTask.steps
        for step in self.steps:
            step._bindTask(self)
        self.updateStatus()

    async def run(self, reportSpeed: Callable[[int], None], waitForSpeedLimit: Callable[[], None]) -> None:
        currentStep = None
        try:
            for step in self.pendingSteps():
                currentStep = step
                await step.run(reportSpeed, waitForSpeedLimit)
        except asyncio.CancelledError:
            logger.info("{} stopped", self.name)
            raise
        except TaskError as e:
            if currentStep is not None:
                currentStep.setError(StepError(e.message, e.params))
            logger.opt(exception=e).error("{} failed", self.name)
            raise
        except Exception as e:
            if currentStep is not None:
                currentStep.setError(StepError(
                    "发生了意外错误：{detail}",
                    {"detail": str(e) or type(e).__name__}
                ))
            logger.opt(exception=e).error("{} failed", self.name)
            raise

    def toDict(self) -> dict:
        from app.models.serialization import toDict
        return toDict(self)

    @classmethod
    def fromDict(cls, data) -> Task:
        from app.models.serialization import fromDict
        return fromDict(data, cls)

    def __hash__(self) -> int:
        return hash(self.taskId)
