from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from shutil import disk_usage
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from shutil import move
from typing import TYPE_CHECKING

from loguru import logger

from app.config.cfg import cfg
from app.config.paths import APP_DATA_DIR
from app.platform.filesystem import deletePath, isExisting, splitStemExt
from app.signal import Signal

if TYPE_CHECKING:
    from app.models.task import Task


@dataclass
class ChecksumWork:
    workId: str = ""
    progress: int = 0


class NameConflictChoice(StrEnum):
    KEEP_BOTH = "keepBoth"
    OVERWRITE = "overwrite"
    ASK = "ask"


@dataclass(frozen=True)
class AddResult:
    replacedTasks: list[Task]
    isOverwriteFailed: bool


@dataclass(frozen=True)
class Placeholders:
    outputFolder: Path
    name: str
    paths: list[Path]


class TaskStore:
    def __init__(self, deleteRecoverably: Callable[[Path], bool]):
        self._tasks: dict[str, Task] = {}
        self._loaded = False
        self._path = APP_DATA_DIR / "tasks.jsonl"
        self._deleteRecoverably = deleteRecoverably
        self._placeholders: dict[str, Placeholders] = {}
        self._taskByPlaceholder: dict[Path, Task] = {}

    def add(self, task: Task, choice: NameConflictChoice) -> AddResult | None:
        task.outputFolder.mkdir(parents=True, exist_ok=True)
        isOverwriteFailed = False
        stem, ext = splitStemExt(task.name)
        index = 0
        while True:
            try:
                self._createPlaceholders(task)
                break
            except FileExistsError as error:
                takenPath = Path(error.filename)
            isUnfinished = self._isUnfinishedPlaceholder(takenPath)
            if not isUnfinished and choice == NameConflictChoice.ASK:
                return None
            if not isUnfinished and choice == NameConflictChoice.OVERWRITE:
                if self._deleteRecoverably(takenPath):
                    continue
                isOverwriteFailed = True
                choice = NameConflictChoice.KEEP_BOTH
            index += 1
            task.setName(f"{stem}({index}){ext}")
        replacedTasks: list[Task] = []
        for path in task.placeholderPaths:
            replaced = self._taskByPlaceholder.get(path)
            if replaced is not None and replaced not in replacedTasks:
                replacedTasks.append(replaced)
        for replaced in replacedTasks:
            self.remove(replaced.taskId)
        self._tasks[task.taskId] = task
        self._setPlaceholders(task)
        return AddResult(replacedTasks, isOverwriteFailed)

    def updatePlaceholders(self, task: Task) -> None:
        from app.models.task import deletePlaceholder
        placeholders = self._placeholders[task.taskId]
        if task.placeholderPaths == placeholders.paths:
            return
        task.outputFolder.mkdir(parents=True, exist_ok=True)
        stem, ext = splitStemExt(task.name)
        index = 0
        while True:
            try:
                self._createPlaceholders(task)
                break
            except FileExistsError:
                index += 1
                task.setName(f"{stem}({index}){ext}")
        newPaths = task.placeholderPaths
        if (task.outputFolder, task.name) != (placeholders.outputFolder, placeholders.name):
            oldPaths = task.placeholderPathsAt(placeholders.outputFolder, placeholders.name)
            for oldPath, newPath in zip(oldPaths, newPaths):
                if oldPath not in placeholders.paths:
                    continue
                for old, new in ((oldPath, newPath), (Path(f"{oldPath}.ghd"), Path(f"{newPath}.ghd"))):
                    if old.exists():
                        deletePath(new)
                        move(old, new)
        for path in placeholders.paths:
            if path not in newPaths:
                deletePlaceholder(path)
        self._setPlaceholders(task)

    def remove(self, taskId: str) -> Task | None:
        self._removePlaceholders(taskId)
        return self._tasks.pop(taskId, None)

    def probeConflict(self, task: Task, folder: Path) -> Path | None:
        paths = sorted(folder / path.relative_to(task.outputFolder) for path in task.placeholderPaths)
        return next((path for path in paths if isExisting(path) and not self._isUnfinishedPlaceholder(path)), None)

    def _isUnfinishedPlaceholder(self, path: Path) -> bool:
        from app.models.task import TaskStatus
        task = self._taskByPlaceholder.get(path)
        return task is not None and task.status != TaskStatus.COMPLETED

    def _createPlaceholders(self, task: Task) -> None:
        from app.models.task import deletePlaceholder
        placeholders = self._placeholders.get(task.taskId)
        existingPaths = placeholders.paths if placeholders else []
        created: list[Path] = []
        try:
            for path in task.placeholderPaths:
                if path in existingPaths:
                    continue
                if task.isOutputFolder and path == Path(task.outputPath):
                    path.mkdir()
                else:
                    path.touch(exist_ok=False)
                created.append(path)
        except FileExistsError:
            for path in created:
                deletePlaceholder(path)
            raise
        for path in created:
            deletePath(Path(f"{path}.ghd"))

    def _setPlaceholders(self, task: Task) -> None:
        self._removePlaceholders(task.taskId)
        paths = task.placeholderPaths
        self._placeholders[task.taskId] = Placeholders(task.outputFolder, task.name, paths)
        for path in paths:
            self._taskByPlaceholder[path] = task

    def _removePlaceholders(self, taskId: str) -> None:
        placeholders = self._placeholders.pop(taskId, None)
        if placeholders is None:
            return
        for path in placeholders.paths:
            task = self._taskByPlaceholder.get(path)
            if task is not None and task.taskId == taskId:
                del self._taskByPlaceholder[path]

    def taskById(self, taskId: str) -> Task | None:
        return self._tasks.get(taskId)

    @property
    def tasks(self) -> dict[str, Task]:
        return self._tasks

    def flush(self) -> None:
        if not self._loaded:
            return

        lines: list[str] = []
        for task in self._tasks.values():
            try:
                lines.append(json.dumps(task.toDict(), ensure_ascii=False) + "\n")
            except Exception as e:
                logger.opt(exception=e).error("failed to serialize task {}", task.taskId)

        tempFile = self._path.with_name(self._path.name + ".tmp")
        try:
            tempFile.parent.mkdir(parents=True, exist_ok=True)
            with open(tempFile, "w", encoding="utf-8") as f:
                f.writelines(lines)
            tempFile.replace(self._path)
        except Exception as e:
            logger.opt(exception=e).error("failed to write tasks.jsonl")

    def loadSaved(self) -> list[Task]:
        from app.models.task import Task

        tasks: list[Task] = []
        if not self._path.exists():
            self._loaded = True
            return tasks

        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    task = Task.fromDict(json.loads(line))
                    self._tasks[task.taskId] = task
                    self._setPlaceholders(task)
                    tasks.append(task)
                except Exception as e:
                    logger.opt(exception=e).error("failed to parse task record")

        self._loaded = True
        return tasks


class TaskQueue:
    def __init__(self):
        self._waiting: list[str] = []
        self._running: dict[str, str] = {}

    def wait(self, taskId: str) -> None:
        if taskId not in self._waiting:
            self._waiting.append(taskId)

    def cancel(self, taskId: str) -> None:
        if taskId in self._waiting:
            self._waiting.remove(taskId)
        self._running.pop(taskId, None)

    def run(self, taskId: str, workId: str) -> None:
        self._running[taskId] = workId

    def done(self, taskId: str) -> None:
        self._running.pop(taskId, None)

    def workIdOf(self, taskId: str) -> str | None:
        return self._running.get(taskId)

    def isRunning(self, taskId: str) -> bool:
        return taskId in self._running

    def isWaiting(self, taskId: str) -> bool:
        return taskId in self._waiting

    def waitingOrder(self) -> list[str]:
        return list(self._waiting)

    def moveToFront(self, taskIds: list[str]) -> bool:
        targets = [tid for tid in self._waiting if tid in set(taskIds)]
        if not targets:
            return False
        for tid in targets:
            self._waiting.remove(tid)
        self._waiting[:0] = targets
        return True

    def runningCount(self) -> int:
        return len(self._running)

    def runningIds(self) -> list[str]:
        return list(self._running)

    def nextWaiting(self) -> str | None:
        return self._waiting.pop(0) if self._waiting else None


class TaskService:
    taskAdded = Signal(object)
    taskRemoved = Signal(str)
    taskStarted = Signal(object)
    taskPaused = Signal(object)
    taskCompleted = Signal(object)
    taskFailed = Signal(object)
    tasksAllCompleted = Signal()
    seedingStarted = Signal(object)
    seedingStopped = Signal(object)
    checksumStarted = Signal(object)
    checksumCompleted = Signal(object, str)
    checksumStopped = Signal(object, object)
    queueChanged = Signal()
    fileDisappeared = Signal(object)
    fileDeleteDenied = Signal()
    diskSpaceInsufficient = Signal(int, int)
    nameConflicted = Signal(object)
    overwriteFailed = Signal(object)

    def __init__(self, coroutineRunner, categoryService, speedMeter, fileWatcher,
                 deleteRecoverably: Callable[[Path], bool],
                 nameConflictChoice: Callable[[], NameConflictChoice]):
        self._coroutineRunner = coroutineRunner
        self._nameConflictChoice = nameConflictChoice
        self._categoryService = categoryService
        self._speedMeter = speedMeter
        self._store = TaskStore(deleteRecoverably)
        self._queue = TaskQueue()
        self._seeding: dict[str, str] = {}
        self._checksums: dict[str, ChecksumWork] = {}
        self._fileWatcher = fileWatcher
        self._watchedPaths: dict[str, str] = {}
        self._fileWatcher.fileChanged.connect(self._onWatchedFileChanged)
        self._hasNotifiedDeleteDenied = False
        self._flushWorkId: str | None = None

        cfg.maxTaskNum.valueChanged.connect(self._rebalance)

    @property
    def tasks(self) -> list[Task]:
        return list(self._store.tasks.values())

    def taskById(self, taskId: str) -> Task | None:
        return self._store.taskById(taskId)

    def runningCount(self) -> int:
        return self._queue.runningCount()

    def runningProgress(self) -> float:
        from app.models.task import TaskStatus
        totalReceived = 0
        totalSize = 0
        for task in self._store.tasks.values():
            if task.status != TaskStatus.RUNNING:
                continue
            _, _, receivedBytes = task.currentSnapshot()
            if task.fileSize > 0:
                totalReceived += receivedBytes
                totalSize += task.fileSize
        if totalSize == 0:
            return -1.0
        return min(100.0, totalReceived / totalSize * 100)

    def add(self, task: Task, autoStart=True, choice: NameConflictChoice | None = None) -> bool:
        if task.taskId in self._store.tasks:
            return True
        task.category, task.outputFolder = self._categoryService.outputFolderOf(task)
        task.shouldSeed = True
        result = self._store.add(task, choice or self._nameConflictChoice())
        if result is None:
            self.nameConflicted.emit(task)
            return False
        if result.isOverwriteFailed:
            self.overwriteFailed.emit(task)
        for replaced in result.replacedTasks:
            self._unwatchFile(replaced)
            self._cancelWork(replaced)
            self.taskRemoved.emit(replaced.taskId)
        self._flushSoon()
        self.taskAdded.emit(task)
        if not autoStart:
            return True
        if task.fileSize > 0:
            try:
                free = disk_usage(task.outputFolder).free
                if free < task.fileSize:
                    self.diskSpaceInsufficient.emit(free, task.fileSize)
                    return True
            except OSError:
                pass
        self._schedule(task)
        return True

    def probeConflict(self, task: Task) -> Path | None:
        _, folder = self._categoryService.outputFolderOf(task)
        return self._store.probeConflict(task, folder)

    def start(self, task: Task) -> None:
        if self._queue.isRunning(task.taskId) or self._queue.isWaiting(task.taskId):
            return
        self._schedule(task)

    def startSeeding(self, task: Task) -> None:
        task.shouldSeed = True
        self._flushSoon()
        self._seed(task, isManual=True)

    def stopSeeding(self, task: Task) -> None:
        task.shouldSeed = False
        self._flushSoon()
        self._cancelWork(task)
        self._refreshSpeedMeter()

    def checksumProgress(self, task: Task) -> int | None:
        work = self._checksums.get(task.taskId)
        return work.progress if work else None

    def startChecksum(self, task: Task, algorithm: str) -> None:
        from app.checksum import toChecksum
        work = ChecksumWork()
        self._checksums[task.taskId] = work
        work.workId = self._coroutineRunner.submit(
            toChecksum(Path(task.outputPath), algorithm, lambda p: setattr(work, "progress", p)),
            done=lambda checksum: self._onChecksumDone(task, algorithm, checksum),
            failed=lambda error: self._onChecksumFailed(task, error))
        self.checksumStarted.emit(task)

    def cancelChecksum(self, task: Task) -> None:
        work = self._checksums.pop(task.taskId, None)
        if work is None:
            return
        self._coroutineRunner.cancel(work.workId)
        self.checksumStopped.emit(task, None)

    def pause(self, task: Task) -> None:
        from app.models.task import TaskStatus
        self._cancelWork(task)
        task.setStatus(TaskStatus.PAUSED)
        self._flushSoon()
        self.taskPaused.emit(task)
        self._pump()

    def delete(self, task: Task, shouldDeleteFiles: bool) -> None:
        self.cancelChecksum(task)
        self._unwatchFile(task)
        canDelete = shouldDeleteFiles and self._canDeleteIn(task.outputFolder)
        if shouldDeleteFiles and not canDelete and not self._hasNotifiedDeleteDenied:
            self._hasNotifiedDeleteDenied = True
            self.fileDeleteDenied.emit()
        def onStopped():
            if canDelete:
                task.deleteFiles()
            task.deletePlaceholders()
        self._cancelWork(task, finished=onStopped)
        self._store.remove(task.taskId)
        self._flushSoon()
        self.taskRemoved.emit(task.taskId)
        self._pump()

    def redownload(self, task: Task) -> None:
        self.cancelChecksum(task)
        self._unwatchFile(task)
        def onStopped():
            task.deleteFiles()
            task.reset()
            self._flushSoon()
            self._schedule(task)
        self._cancelWork(task, finished=onStopped)

    def edit(self, task: Task, options: dict, newTask: Task | None = None) -> None:
        self.cancelChecksum(task)
        needsDelete = newTask is not None and not task.canReuseProgress(newTask)
        def onStopped():
            if needsDelete:
                task.deleteFiles()
            if newTask is not None:
                task.replaceWith(newTask)
            task.setOptions(options)
            self._store.updatePlaceholders(task)
            self._flushSoon()
            self._schedule(task)
        self._cancelWork(task, finished=onStopped)

    def setCategory(self, task: Task, categoryId: str) -> None:
        task.category = categoryId
        self._flushSoon()

    def updateSelection(self, task: Task, selectedIndexes: set[int]) -> None:
        from app.models.task import TaskStatus

        selectedSet = set(selectedIndexes)
        wasCompleted = task.status == TaskStatus.COMPLETED

        def apply():
            task.setSelection(selectedSet)
            self._store.updatePlaceholders(task)
            if wasCompleted and task.files and any(f.selected and not f.completed for f in task.files):
                task.completedAt = 0
                self._unwatchFile(task)
                self._cancelWork(task, finished=lambda: self._schedule(task))
            self._flushSoon()

        isRunningDeselected = False
        if self._queue.isRunning(task.taskId):
            for step in task.steps:
                if step.status == TaskStatus.RUNNING:
                    fileIndex = step.fileIndex
                    isRunningDeselected = fileIndex is not None and fileIndex not in selectedSet
                    break

        if isRunningDeselected:
            def onStopped():
                apply()
                self._schedule(task)
            self._cancelWork(task, finished=onStopped)
            return
        apply()

    def startAll(self) -> None:
        from app.models.task import TaskStatus
        for task in self._store.tasks.values():
            if task.status in {TaskStatus.PAUSED, TaskStatus.WAITING, TaskStatus.FAILED}:
                self._schedule(task)

    def pauseAll(self) -> None:
        for task in list(self._store.tasks.values()):
            if self._queue.isRunning(task.taskId) or self._queue.isWaiting(task.taskId):
                self.pause(task)

    def resumeSaved(self) -> None:
        from app.models.task import TaskStatus
        for task in self._store.loadSaved():
            self.taskAdded.emit(task)
            if task.status == TaskStatus.COMPLETED and task.hasOutputFile and isExisting(task.outputPath):
                self._watchFile(task)
                if task.canSeed and task.shouldSeed:
                    self._seed(task)
            elif task.status in {TaskStatus.WAITING, TaskStatus.RUNNING}:
                task.setStatus(TaskStatus.WAITING)
                self._schedule(task)

    def stop(self) -> None:
        from app.models.task import TaskStatus
        for task in self._store.tasks.values():
            if task.status in {TaskStatus.RUNNING, TaskStatus.WAITING}:
                task.setStatus(TaskStatus.PAUSED)

    def waitingOrder(self) -> list[str]:
        return self._queue.waitingOrder()

    def moveToFront(self, taskIds: list[str]) -> None:
        if self._queue.moveToFront(taskIds):
            self.queueChanged.emit()

    def flush(self) -> None:
        if self._flushWorkId is not None:
            self._coroutineRunner.cancel(self._flushWorkId)
            self._flushWorkId = None
        self._store.flush()

    def _flushSoon(self) -> None:
        if self._flushWorkId is not None:
            self._coroutineRunner.cancel(self._flushWorkId)
        self._flushWorkId = self._coroutineRunner.submit(
            self._debouncedFlush(), failed=self._onFlushFailed)

    async def _debouncedFlush(self) -> None:
        await asyncio.sleep(0.2)
        self._coroutineRunner.post(self.flush)

    def _onFlushFailed(self, error) -> None:
        self._flushWorkId = None
        logger.error("Flush failed: {}", error)

    def _schedule(self, task: Task) -> None:
        self._queue.wait(task.taskId)
        self._pump()

    def _dispatch(self, task: Task) -> None:
        from app.models.task import TaskStatus

        task.setStatus(TaskStatus.RUNNING)
        workId = self._coroutineRunner.submit(
            task.run(self._speedMeter.addSpeed, self._speedMeter.waitForSpeedLimit),
            done=lambda _: self._onRunDone(task),
            failed=lambda error: self._onRunFailed(task, error),
        )
        self._queue.run(task.taskId, workId)
        self.taskStarted.emit(task)

    def _seed(self, task: Task, isManual: bool = False) -> None:
        task.isSeeding = True
        self._seeding[task.taskId] = self._coroutineRunner.submit(
            task.runSeeding(isManual),
            done=lambda _: self._onSeedingDone(task),
            failed=lambda _: self._onSeedingEnded(task),
        )
        self.seedingStarted.emit(task)
        self._refreshSpeedMeter()

    def _onSeedingDone(self, task: Task) -> None:
        task.shouldSeed = False
        self._onSeedingEnded(task)

    def _onSeedingEnded(self, task: Task) -> None:
        self._seeding.pop(task.taskId, None)
        task.isSeeding = False
        self._flushSoon()
        self.seedingStopped.emit(task)
        self._refreshSpeedMeter()

    def _canDeleteIn(self, folder: Path) -> bool:
        if sys.platform != "darwin":
            return True
        try:
            next(folder.iterdir(), None)
            return True
        except PermissionError:
            return False
        except OSError:
            return True

    def _onChecksumDone(self, task: Task, algorithm: str, checksum: str) -> None:
        del self._checksums[task.taskId]
        task.checksums[algorithm] = checksum
        self._flushSoon()
        self.checksumCompleted.emit(task, algorithm)

    def _onChecksumFailed(self, task: Task, error: Exception) -> None:
        from app.models.task import TaskError
        del self._checksums[task.taskId]
        self.checksumStopped.emit(task, TaskError("无法读取文件：{detail}", detail=str(error)))

    def _cancelWork(self, task: Task, finished: Callable = None) -> None:
        workId = self._queue.workIdOf(task.taskId) or self._seeding.pop(task.taskId, None)
        self._queue.cancel(task.taskId)
        if task.isSeeding:
            task.isSeeding = False
            self.seedingStopped.emit(task)
        if workId is not None:
            self._coroutineRunner.cancel(workId, finished=finished)
        elif finished is not None:
            finished()

    def _rebalance(self, *_args) -> None:
        from app.models.task import TaskStatus
        for taskId in self._queue.runningIds()[cfg.maxTaskNum.value:]:
            task = self._store.taskById(taskId)
            if task is not None and task.canPause:
                self._cancelWork(task)
                task.setStatus(TaskStatus.WAITING)
                self._queue.wait(taskId)
        self._pump()

    def _pump(self) -> None:
        while self._queue.runningCount() < cfg.maxTaskNum.value:
            taskId = self._queue.nextWaiting()
            if taskId is None:
                break
            task = self._store.taskById(taskId)
            if task is not None:
                self._dispatch(task)
        self._refreshSpeedMeter()

    def _refreshSpeedMeter(self) -> None:
        if self._queue.runningCount() or self._seeding:
            self._speedMeter.start()
        else:
            self._speedMeter.stop()

    def _onRunDone(self, task: Task) -> None:
        from app.models.task import TaskStatus
        self._queue.done(task.taskId)
        self._flushSoon()
        self.taskCompleted.emit(task)
        if task.hasOutputFile:
            self._watchFile(task)
        if task.status == TaskStatus.COMPLETED and task.canSeed and task.shouldSeed:
            self._seed(task)
        self._pump()
        if self._queue.runningCount() == 0:
            self.tasksAllCompleted.emit()

    def _onRunFailed(self, task: Task, error: Exception) -> None:
        self._queue.done(task.taskId)
        self._flushSoon()
        self.taskFailed.emit(task)
        self._pump()
        if self._queue.runningCount() == 0:
            self.tasksAllCompleted.emit()

    def _watchFile(self, task: Task) -> None:
        path = task.outputPath
        self._watchedPaths[path] = task.taskId
        self._fileWatcher.addPath(path)

    def _unwatchFile(self, task: Task) -> None:
        path = task.outputPath
        self._watchedPaths.pop(path, None)
        self._fileWatcher.removePath(path)

    def _onWatchedFileChanged(self, path: str) -> None:
        if isExisting(path):
            return
        taskId = self._watchedPaths.pop(path, None)
        if taskId is None:
            return
        task = self._store.taskById(taskId)
        if task is not None:
            self._cancelWork(task)
            self.fileDisappeared.emit(task)
