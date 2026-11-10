from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from enum import auto, IntEnum
from pathlib import Path
from time import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, ClassVar, Self
from urllib.parse import urlparse
from uuid import uuid4

from loguru import logger

from app.config.cfg import cfg, currentHeaders
from app.platform.filesystem import deletePath, splitStemExt, toSafeFilename

# urllib 遇到方括号会抛 ValueError（如 ed2k 文件名），链接文本一律经 toScheme / toHost 取协议头和 host
SCHEME_PATTERN = re.compile(r"([A-Za-z][A-Za-z0-9+.-]+):")  # 单字母是 Windows 盘符


def toScheme(url: str) -> str:
    match = SCHEME_PATTERN.match(url.strip())
    return match[1].lower() if match else ""


def toHost(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except ValueError:
        return ""


def deletePlaceholder(path: Path) -> None:
    if path.is_dir() and not any(path.iterdir()):
        path.rmdir()
    elif path.is_file() and path.stat().st_size == 0:
        path.unlink()


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
    def __init__(self, message: str, **params: Any):
        super().__init__(message)
        self.message = message
        self.params = params

    def __str__(self) -> str:
        return self.message.format_map(self.params) if self.params else self.message

    def toDict(self) -> dict[str, Any]:
        return {"message": self.message, "params": {k: str(v) for k, v in self.params.items()}}


def toTaskError(error: BaseException) -> TaskError:
    if isinstance(error, TaskError):
        return error
    return TaskError("发生了意外错误：{detail}", detail=str(error) or type(error).__name__)


WEB_PAGE_SUFFIXES = {".asp", ".aspx", ".cgi", ".jsp", ".php"}


@dataclass(frozen=True)
class RemoteFile:
    name: str
    fileSize: int
    canUseRangeRequests: bool
    lastModified: str = ""
    contentType: str = ""

    def matchType(self, suffixes: set[str], contentTypes: set[str]) -> bool:
        suffix = Path(self.name).suffix.lower()
        if suffix and suffix not in WEB_PAGE_SUFFIXES:
            return suffix in suffixes
        return self.contentType in contentTypes


@dataclass(frozen=True)
class TaskOptions:
    url: str
    outputFolder: Path = field(default_factory=lambda: Path(cfg.downloadFolder.value))
    headers: dict[str, str] = field(default_factory=currentHeaders)
    clientProfile: str = ""
    userAgent: str = ""
    sourceUserAgent: str = ""
    subworkerCount: int = field(default_factory=lambda: cfg.preBlockNum.value)
    file: RemoteFile | None = None

    @classmethod
    def fromOptions(cls, options: dict) -> TaskOptions:
        from app.models.serialization import filterFields
        return cls(**filterFields(cls, options))

    @property
    def isProbed(self) -> bool:
        return self.file is not None


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
    _registry: ClassVar[dict[str, type[TaskStep]]] = {}
    canPause: ClassVar[bool] = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        TaskStep._registry[f"{cls.__module__}.{cls.__name__}"] = cls

    stepIndex: int
    fileIndex: int | None = None
    stepId: str = field(default_factory=lambda: f"stp_{uuid4().hex}")
    status: TaskStatus = TaskStatus.WAITING
    progress: float = 0
    receivedBytes: int = 0
    speed: int = 0
    error: TaskError | None = field(default=None, repr=False, init=False)
    _task: Task = field(repr=False, init=False)

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

    def setError(self, error: TaskError) -> None:
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

    def setOptions(self, options: dict[str, Any]) -> None:
        pass

    async def run(
        self,
        reportSpeed: Callable[[int], None],
        waitForSpeedLimit: Callable[[], Awaitable[None]],
    ) -> None:
        raise NotImplementedError

    @property
    def outputPath(self) -> str:
        return ""

    @classmethod
    def fromFile(cls, file: TaskFile, task: Task) -> TaskStep:
        raise NotImplementedError

    def toDict(self) -> dict[str, Any]:
        from app.models.serialization import toDict
        return toDict(self)

    @classmethod
    def fromDict(cls, data: Any) -> Self:
        from app.models.serialization import fromDict
        return fromDict(data, cls)


@dataclass(kw_only=True, eq=False)
class Task:
    _registry: ClassVar[dict[str, type[Task]]] = {}
    canEdit: ClassVar[bool] = False
    fileType: ClassVar[type[TaskFile]] = TaskFile
    hasOutputFile: ClassVar[bool] = True
    canSeed: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Task._registry[f"{cls.__module__}.{cls.__name__}"] = cls

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
    shouldSeed: bool = False
    checksums: dict[str, str] = field(default_factory=dict)
    isSeeding: bool = field(default=False, init=False, repr=False)

    @property
    def outputPath(self) -> str:
        return str(self.outputFolder / self.name)

    @property
    def isOutputFolder(self) -> bool:
        return len(self.files or []) > 1

    def toFilePath(self, fileIndex: int | None) -> Path:
        if self.isOutputFolder:
            for file in self.files:
                if file.index == fileIndex:
                    return Path(self.outputPath, file.relativePath)
        return Path(self.outputPath)

    def toDisplayPath(self, file: TaskFile) -> str:
        return file.relativePath

    def toSidePath(self, fileIndex: int | None, suffix: str) -> Path:
        path = self.toFilePath(fileIndex)
        isFolder = self.isOutputFolder and path == Path(self.outputPath)
        stem = path.name if isFolder else splitStemExt(path.name)[0]
        return path.with_name(f"{stem}.{suffix}")

    @property
    def partPath(self) -> Path:
        return Path(f"{self.outputPath}.ghd")

    @property
    def placeholderPaths(self) -> list[Path]:
        if not self.hasOutputFile:
            return []
        paths = [Path(self.outputPath)]
        for step in self.steps:
            if self.isOutputFolder and step.fileIndex is not None:
                continue
            path = Path(step.outputPath)
            if step.outputPath and path.parent == self.outputFolder and path not in paths:
                paths.append(path)
        return paths

    def placeholderPathsAt(self, outputFolder: Path, name: str) -> list[Path]:
        current = self.outputFolder, self.name
        self.outputFolder, self.name = outputFolder, name
        try:
            return self.placeholderPaths
        finally:
            self.outputFolder, self.name = current

    @property
    def canPause(self) -> bool:
        for step in self.steps:
            if step.status == TaskStatus.RUNNING:
                return step.canPause
        return True

    @property
    def lastError(self) -> TaskError | None:
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

    def setOptions(self, options: dict[str, Any]) -> None:
        newFolder = options.get("outputFolder")
        if isinstance(newFolder, (str, Path)):
            self.outputFolder = Path(newFolder)
        if "category" in options:
            self.category = options["category"]
        for step in self.steps:
            step.setOptions(options)

    @property
    def selectedIndexes(self) -> set[int]:
        return {file.index for file in self.files or [] if file.selected}

    def isStepSelected(self, step: TaskStep, selectedIndexes: set[int]) -> bool:
        return not self.files or step.fileIndex is None or step.fileIndex in selectedIndexes

    def _updateFilesFromSteps(self) -> None:
        if not self.files:
            return
        received: dict[int, int] = {}
        completed: dict[int, bool] = {}
        for step in self.steps:
            fileIndex = step.fileIndex
            if fileIndex is None:
                continue
            received[fileIndex] = received.get(fileIndex, 0) + step.receivedBytes
            completed[fileIndex] = completed.get(fileIndex, True) and step.status == TaskStatus.COMPLETED
        for file in self.files:
            if file.index in received:
                file.downloadedBytes = received[file.index]
                file.completed = completed[file.index]

    def currentSnapshot(self) -> tuple[float, int, int]:
        selectedIndexes = self.selectedIndexes
        steps = [s for s in self.steps if self.isStepSelected(s, selectedIndexes)]
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
        selectedIndexes = self.selectedIndexes
        steps = [s for s in self.steps if self.isStepSelected(s, selectedIndexes)]
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
        selectedIndexes = self.selectedIndexes
        steps = [s for s in self.steps if self.isStepSelected(s, selectedIndexes)]
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
        self.shouldSeed = True
        self.checksums = {}
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

    def setSelection(self, selectedIndexes: Iterable[int]) -> None:
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
            if not self.isStepSelected(step, self.selectedIndexes):
                continue
            if step.status == TaskStatus.COMPLETED:
                continue
            yield step

    def deleteFiles(self) -> None:
        for path in self.placeholderPaths:
            if path.is_dir():
                for child in path.iterdir():
                    deletePath(child)
            elif path.is_file():
                os.truncate(path, 0)
            deletePath(Path(f"{path}.ghd"))

    def relink(self, newTask: Task) -> None:
        raise TaskError("该链接不能用于更换")

    async def run(
        self,
        reportSpeed: Callable[[int], None],
        waitForSpeedLimit: Callable[[], Awaitable[None]],
    ) -> None:
        currentStep = None
        try:
            for step in self.pendingSteps():
                currentStep = step
                if step.outputPath:
                    Path(step.outputPath).parent.mkdir(parents=True, exist_ok=True)
                await step.run(reportSpeed, waitForSpeedLimit)
                step.setStatus(TaskStatus.COMPLETED)
            if self.status == TaskStatus.COMPLETED:
                deletePath(self.partPath)
        except asyncio.CancelledError:
            logger.info("{} stopped", self.name)
            raise
        except Exception as e:
            if currentStep is not None:
                currentStep.setError(toTaskError(e))
            logger.opt(exception=e).error("{} failed", self.name)
            raise

    def deletePlaceholders(self) -> None:
        for step in self.steps:
            outputPath = step.outputPath
            if outputPath and step.status != TaskStatus.COMPLETED:
                deletePath(Path(outputPath))
                deletePath(Path(f"{outputPath}.ghd"))
        for path in self.placeholderPaths:
            deletePlaceholder(path)
            deletePath(Path(f"{path}.ghd"))

    async def runSeeding(self, isManual: bool) -> None:
        raise NotImplementedError

    def toDict(self) -> dict[str, Any]:
        from app.models.serialization import toDict
        return toDict(self)

    @classmethod
    def fromDict(cls, data: Any) -> Self:
        from app.models.serialization import fromDict
        return fromDict(data, cls)

    def __hash__(self) -> int:
        return hash(self.taskId)
