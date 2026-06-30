from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import auto, IntEnum
from pathlib import Path
from time import time
from typing import ClassVar, Type, Iterable
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


@dataclass(frozen=True)
class TaskOptions:
    url: str
    outputFolder: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))
    headers: dict[str, str] = field(
        default_factory=lambda: dict(cfg.defaultRequestHeaders.value)
    )
    clientProfile: str = ""
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
    error: str = ""

    def _bindTask(self, task: Task):
        self._task = task

    @property
    def task(self) -> Task:
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

    def setError(self, error, sync: bool = True):
        while isinstance(error, BaseExceptionGroup) and error.exceptions:
            error = error.exceptions[0]
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

    def setOptions(self, options: dict) -> None:
        pass

    async def run(self) -> None:
        raise NotImplementedError

    def deleteFiles(self):
        pass

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
    stepType: Type[TaskStep] | None = field(default=None, repr=False)

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
    def lastError(self) -> str:
        for step in reversed(self.steps):
            if step.status == TaskStatus.FAILED and step.error:
                return step.error
        for step in reversed(self.steps):
            if step.error:
                return step.error
        return ""

    def __post_init__(self):
        self.name = toSafeFilename(self.name, fallback="download")
        for step in self.steps:
            step._bindTask(self)
        self.updateStatus()

    def setName(self, name: str):
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
        from shutil import move
        oldFolder = self.outputFolder
        newFolder.mkdir(parents=True, exist_ok=True)
        for step in self.steps:
            oldPath = Path(step.outputPath)
            if not oldPath.exists():
                continue
            try:
                relPath = oldPath.relative_to(oldFolder)
            except ValueError:
                continue
            newPath = newFolder / relPath
            newPath.parent.mkdir(parents=True, exist_ok=True)
            move(str(oldPath), str(newPath))
            ghdPath = Path(f"{oldPath}.ghd")
            if ghdPath.exists():
                move(str(ghdPath), str(newFolder / f"{relPath}.ghd"))
            storedFile = getattr(step, "outputFile", "")
            if storedFile:
                try:
                    step.outputFile = str(newFolder / Path(storedFile).relative_to(oldFolder))
                except ValueError:
                    pass
        self.outputFolder = newFolder

    def currentSnapshot(self) -> tuple[float, int, int]:
        if not self.steps:
            return 0.0, 0, 0
        progress = 0.0
        speed = 0
        receivedBytes = 0
        for step in self.steps:
            progress += step.progress
            speed += step.speed
            receivedBytes += step.receivedBytes
        return progress / len(self.steps), speed, receivedBytes

    def updateStatus(self) -> TaskStatus:
        if not self.steps:
            return self.status
        statuses = [step.status for step in self.steps]
        if any(s == TaskStatus.FAILED for s in statuses):
            self.status = TaskStatus.FAILED
        elif all(s == TaskStatus.COMPLETED for s in statuses):
            self.status = TaskStatus.COMPLETED
            if not self.completedAt:
                self.completedAt = int(time())
        elif any(s == TaskStatus.RUNNING for s in statuses):
            self.status = TaskStatus.RUNNING
        elif all(s == TaskStatus.PAUSED for s in statuses):
            self.status = TaskStatus.PAUSED
        else:
            self.status = TaskStatus.WAITING
        return self.status

    def setStatus(self, status: TaskStatus) -> TaskStatus:
        if not self.steps:
            self.status = status
            return self.status
        for step in self.steps:
            if step.status == TaskStatus.COMPLETED:
                continue
            if status == TaskStatus.RUNNING and step.status == TaskStatus.FAILED:
                step.reset(sync=False)
            step.setStatus(status, sync=False)
        return self.updateStatus()

    def reset(self) -> TaskStatus:
        self.completedAt = 0
        if not self.steps:
            self.status = TaskStatus.WAITING
            return self.status
        for step in self.steps:
            step.reset(sync=False)
        return self.updateStatus()

    def addStep(self, step: TaskStep):
        step._bindTask(self)
        self.steps.append(step)
        self.updateStatus()

    def removeStep(self, step: TaskStep):
        self.steps.remove(step)
        self.updateStatus()

    def setSelection(self, selectedIndexes: list[int]):
        if self.files is None or self.stepType is None:
            return
        selectedSet = set(selectedIndexes)
        for file in self.files:
            file.selected = file.index in selectedSet
        stepsToRemove = [
            step for step in self.steps
            if (fileIndex := getattr(step, "fileIndex", None)) is not None
            and fileIndex not in selectedSet
        ]
        for step in stepsToRemove:
            self.steps.remove(step)
        existingFileIndexes = {
            fileIndex
            for step in self.steps
            if (fileIndex := getattr(step, "fileIndex", None)) is not None
        }
        for file in self.files:
            if file.selected and file.index not in existingFileIndexes:
                newStep = self.stepType.fromFile(file, self)
                self.addStep(newStep)
        self.fileSize = sum(f.size for f in self.files if f.selected)
        self.updateStatus()

    def pendingSteps(self) -> Iterable[TaskStep]:
        self.steps.sort(key=lambda step: step.stepIndex)
        for step in self.steps:
            if self.status != TaskStatus.RUNNING:
                break
            if step.status == TaskStatus.COMPLETED:
                continue
            yield step

    def deleteFiles(self):
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

    async def run(self):
        currentStep = None
        try:
            for step in self.pendingSteps():
                currentStep = step
                await step.run()
        except asyncio.CancelledError:
            logger.info("{} stopped", self.name)
            raise
        except Exception as e:
            if currentStep is not None and not currentStep.error:
                currentStep.setError(e)
            logger.opt(exception=e).error("{} failed", self.name)
            raise

    def toDict(self) -> dict:
        from app.models.serialization import toDict
        return toDict(self)

    @classmethod
    def fromDict(cls, data) -> Task:
        from app.models.serialization import fromDict
        return fromDict(data, cls)

    def __hash__(self):
        return hash(self.taskId)
