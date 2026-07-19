from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from loguru import logger

from app.config.cfg import cfg
from app.config.paths import APP_DATA_DIR

if TYPE_CHECKING:
    from app.models.task import Task


@dataclass(frozen=True)
class AheadDownloadRevision:
    updateTask: Callable[[], None] | None
    shouldDeleteFiles: bool


class TaskStore:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._loaded = False
        self._path = Path(APP_DATA_DIR) / "tasks.jsonl"

    def add(self, task: Task) -> None:
        self._tasks[task.taskId] = task

    def remove(self, taskId: str) -> Task | None:
        return self._tasks.pop(taskId, None)

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

    def runningCount(self) -> int:
        return len(self._running)

    def runningIds(self) -> list[str]:
        return list(self._running)

    def nextWaiting(self) -> str | None:
        return self._waiting.pop(0) if self._waiting else None


class TaskService(QObject):
    taskAdded = Signal(object)
    taskRemoved = Signal(str)
    taskStarted = Signal(object)
    taskPaused = Signal(object)
    taskCompleted = Signal(object)
    taskFailed = Signal(object)
    tasksAllCompleted = Signal()
    fileDisappeared = Signal(object)
    diskSpaceInsufficient = Signal(int, int)
    aheadDownloadUpdated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store = TaskStore()
        self._aheadTasks: dict[str, Task] = {}
        self._aheadRevisions: dict[str, list[AheadDownloadRevision]] = {}
        self._stoppingAhead: set[str] = set()
        self._discardingAhead: set[str] = set()
        self._ignoredRunTaskIds: set[str] = set()
        self._queue = TaskQueue()
        self._fileWatcher = QFileSystemWatcher(self)
        self._watchedPaths: dict[str, str] = {}
        self._fileWatcher.fileChanged.connect(self._onWatchedFileChanged)

        self._flushTimer = QTimer(self)
        self._flushTimer.setSingleShot(True)
        self._flushTimer.setInterval(200)
        self._flushTimer.timeout.connect(self._store.flush)

        cfg.maxTaskNum.valueChanged.connect(self._rebalance)

    @property
    def tasks(self) -> list[Task]:
        return list(self._store.tasks.values())

    def taskById(self, taskId: str) -> Task | None:
        return self._store.taskById(taskId)

    def _taskById(self, taskId: str) -> Task | None:
        return self._store.taskById(taskId) or self._aheadTasks.get(taskId)

    def _hasActivePublicTasks(self) -> bool:
        from app.models.task import TaskStatus
        return any(
            task.status in {TaskStatus.RUNNING, TaskStatus.WAITING}
            for task in self._store.tasks.values()
        )

    def _isAheadDownload(self, taskId: str) -> bool:
        return taskId in self._aheadTasks or taskId in self._stoppingAhead

    def _isPublishedTask(self, task: Task) -> bool:
        return self._store.taskById(task.taskId) is task and not self._isAheadDownload(task.taskId)

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

    def add(self, task: Task) -> None:
        if self._aheadTasks.pop(task.taskId, None) is not None:
            self._store.add(task)
            self._flushTimer.start()
            self.taskAdded.emit(task)
            if task.taskId in self._stoppingAhead:
                return
            from app.models.task import TaskStatus
            if task.status == TaskStatus.COMPLETED:
                if self._queue.isRunning(task.taskId):
                    self._ignoredRunTaskIds.add(task.taskId)
                self.taskCompleted.emit(task)
                if task.hasOutputFile:
                    self._watchFile(task)
                if not self._hasActivePublicTasks():
                    self.tasksAllCompleted.emit()
            elif task.status == TaskStatus.FAILED:
                if self._queue.isRunning(task.taskId):
                    self._ignoredRunTaskIds.add(task.taskId)
                else:
                    self._schedule(task)
            elif not self._queue.isRunning(task.taskId) and not self._queue.isWaiting(task.taskId):
                if self._hasDiskSpace(task, shouldNotify=True):
                    self._schedule(task)
            return
        if task.taskId in self._store.tasks:
            return
        if task.taskId in self._stoppingAhead:
            self._store.add(task)
            self._flushTimer.start()
            self.taskAdded.emit(task)
            return
        self._updateTaskDefaults(task)
        self._store.add(task)
        self._flushTimer.start()
        self.taskAdded.emit(task)
        if self._hasDiskSpace(task, shouldNotify=True):
            self._schedule(task)

    def _updateTaskDefaults(self, task: Task) -> None:
        if cfg.isCategoryEnabled.value:
            from app.services.category_service import categoryService
            if task.category is None:
                task.category = categoryService.categoryOf(task)
            if task.category and task.outputFolder == Path(cfg.downloadFolder.value):
                folder = categoryService.folderOf(task.category)
                if folder:
                    task.outputFolder = Path(folder)
        task.deduplicateFilename()

    def _hasDiskSpace(self, task: Task, shouldNotify: bool) -> bool:
        if task.fileSize <= 0:
            return True
        from shutil import disk_usage
        try:
            free = disk_usage(task.outputFolder).free
        except OSError:
            return True
        if free >= task.fileSize:
            return True
        if shouldNotify:
            self.diskSpaceInsufficient.emit(free, task.fileSize)
        return False

    def startAheadDownload(self, task: Task) -> None:
        if task.taskId in self._store.tasks:
            return
        if task.taskId in self._aheadTasks:
            self._discardingAhead.discard(task.taskId)
            return
        if task.taskId in self._stoppingAhead:
            self._aheadTasks[task.taskId] = task
            self._discardingAhead.discard(task.taskId)
            return
        self._updateTaskDefaults(task)
        self._aheadTasks[task.taskId] = task
        if self._hasDiskSpace(task, shouldNotify=False):
            self._schedule(task)

    def deleteAheadDownload(self, task: Task) -> None:
        if task.taskId not in self._aheadTasks and task.taskId not in self._stoppingAhead:
            return
        self._discardingAhead.add(task.taskId)
        self._updateAheadDownload(task, None, shouldDeleteFiles=True)
        self._pump()

    def setAheadDownloadName(self, task: Task, name: str) -> None:
        canReuseProgress = task.canReuseProgress(task)

        def setTaskName() -> None:
            oldName = task.name
            task.setName(name)
            task.deduplicateFilename()
            newName = task.name
            task.setName(oldName)
            try:
                if canReuseProgress:
                    task.updateName(newName)
                else:
                    task.setName(newName)
            except OSError as e:
                logger.opt(exception=e).warning("failed to move ahead download progress")
                task.reset()

        self._updateAheadDownload(task, setTaskName, not canReuseProgress)

    def setAheadDownloadOptions(self, task: Task, options: dict) -> None:
        self._updateAheadDownload(
            task,
            lambda: task.setOptions(options),
            shouldDeleteFiles=not task.canPause,
        )

    def setAheadDownloadSelection(self, task: Task, selectedIndexes: set[int]) -> None:
        selected = set(selectedIndexes)
        self._updateAheadDownload(
            task,
            lambda: task.setSelection(selected),
            shouldDeleteFiles=False,
        )

    def setAheadDownloadTask(self, task: Task, replacement: Task) -> None:
        canReuseProgress = task.canReuseProgress(replacement)
        if not canReuseProgress:
            replacement.reset()
        self._updateAheadDownload(
            task,
            lambda: task.replaceWith(replacement),
            shouldDeleteFiles=not canReuseProgress,
        )

    def setAheadDownloadCategory(self, task: Task, categoryId: str) -> None:
        def setTaskCategory() -> None:
            task.category = categoryId
            if cfg.isCategoryEnabled.value and task.outputFolder == Path(cfg.downloadFolder.value):
                from app.services.category_service import categoryService
                folder = categoryService.folderOf(categoryId)
                if folder:
                    task.setOptions({"outputFolder": Path(folder)})

        self._updateAheadDownload(
            task,
            setTaskCategory,
            shouldDeleteFiles=not task.canPause,
        )

    def _updateAheadDownload(
        self, task: Task, updateTask: Callable[[], None] | None, shouldDeleteFiles: bool
    ) -> None:
        if task.taskId not in self._aheadTasks and task.taskId not in self._stoppingAhead:
            if updateTask is not None:
                updateTask()
                self.aheadDownloadUpdated.emit(task)
            return
        revision = AheadDownloadRevision(updateTask, shouldDeleteFiles)
        self._aheadRevisions.setdefault(task.taskId, []).append(revision)
        if task.taskId in self._stoppingAhead:
            return
        self._stoppingAhead.add(task.taskId)
        self._cancelRun(task, finished=lambda: self._onAheadDownloadStopped(task))

    def _onAheadDownloadStopped(self, task: Task) -> None:
        revisions = self._aheadRevisions.pop(task.taskId, [])
        hasTarget = task.taskId in self._aheadTasks or task.taskId in self._store.tasks
        shouldDiscard = task.taskId in self._discardingAhead and task.taskId not in self._store.tasks
        if any(revision.shouldDeleteFiles for revision in revisions):
            task.deleteFiles()
            task.reset()
        self._stoppingAhead.discard(task.taskId)
        if hasTarget and not shouldDiscard:
            for revision in revisions:
                if revision.updateTask is not None:
                    revision.updateTask()
            if any(revision.updateTask is not None for revision in revisions):
                self.aheadDownloadUpdated.emit(task)
        if task.taskId in self._discardingAhead:
            self._discardingAhead.discard(task.taskId)
            if shouldDiscard:
                self._aheadTasks.pop(task.taskId, None)
        hasTarget = task.taskId in self._aheadTasks or task.taskId in self._store.tasks
        if hasTarget and task.taskId not in self._stoppingAhead:
            from app.models.task import TaskStatus
            if task.status != TaskStatus.COMPLETED:
                self._schedule(task)

    def start(self, task: Task) -> None:
        if self._queue.isRunning(task.taskId) or self._queue.isWaiting(task.taskId):
            return
        self._schedule(task)

    def pause(self, task: Task) -> None:
        from app.models.task import TaskStatus
        self._cancelRun(task)
        task.setStatus(TaskStatus.PAUSED)
        self._flushTimer.start()
        self.taskPaused.emit(task)

    def delete(self, task: Task, shouldDeleteFiles: bool) -> None:
        self._unwatchFile(task)
        self._cancelRun(task, finished=task.deleteFiles if shouldDeleteFiles else None)
        self._store.remove(task.taskId)
        self._flushTimer.start()
        self.taskRemoved.emit(task.taskId)
        self._pump()

    def redownload(self, task: Task) -> None:
        self._unwatchFile(task)
        def afterStopped():
            task.deleteFiles()
            task.reset()
            self._flushTimer.start()
            self._schedule(task)
        self._cancelRun(task, finished=afterStopped)

    def edit(self, task: Task, options: dict, newTask: Task | None = None) -> None:
        needsDelete = newTask is not None and not task.canReuseProgress(newTask)
        def afterStopped():
            if needsDelete:
                task.deleteFiles()
            if newTask is not None:
                task.replaceWith(newTask)
            task.setOptions(options)
            self._flushTimer.start()
            self._schedule(task)
        self._cancelRun(task, finished=afterStopped)

    def setCategory(self, task: Task, categoryId: str) -> None:
        task.category = categoryId
        self._flushTimer.start()

    def applySelection(self, task: Task, selectedIndexes: set[int]) -> None:
        from app.models.task import TaskStatus

        selectedSet = set(selectedIndexes)
        wasCompleted = task.status == TaskStatus.COMPLETED

        def apply():
            task.setSelection(selectedSet)
            if wasCompleted and task.files and any(f.selected and not f.completed for f in task.files):
                task.completedAt = 0
                self._unwatchFile(task)
                self._schedule(task)
            self._flushTimer.start()

        isRunningDeselected = False
        if self._queue.isRunning(task.taskId):
            for step in task.steps:
                if step.status == TaskStatus.RUNNING:
                    fileIndex = getattr(step, "fileIndex", None)
                    isRunningDeselected = fileIndex is not None and fileIndex not in selectedSet
                    break

        if isRunningDeselected:
            def afterStopped():
                apply()
                self._schedule(task)
            self._cancelRun(task, finished=afterStopped)
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
            if task.status == TaskStatus.COMPLETED and task.hasOutputFile and Path(task.outputPath).exists():
                self._watchFile(task)
            elif task.status in {TaskStatus.WAITING, TaskStatus.RUNNING}:
                task.setStatus(TaskStatus.WAITING)
                self._schedule(task)

    def stop(self) -> None:
        from app.models.task import TaskStatus
        for task in list(self._aheadTasks.values()):
            self.deleteAheadDownload(task)
        for task in self._store.tasks.values():
            if task.status in {TaskStatus.RUNNING, TaskStatus.WAITING}:
                task.setStatus(TaskStatus.PAUSED)

    def deleteStoppedAheadDownloads(self) -> None:
        tasks = list(self._aheadTasks.values())
        self._aheadTasks.clear()
        self._aheadRevisions.clear()
        self._stoppingAhead.clear()
        self._discardingAhead.clear()
        for task in tasks:
            task.deleteFiles()

    def flush(self) -> None:
        self._flushTimer.stop()
        self._store.flush()

    def _schedule(self, task: Task) -> None:
        self._queue.wait(task.taskId)
        self._pump()

    def _dispatch(self, task: Task) -> None:
        from app.models.task import TaskStatus
        from app.services.coroutine_runner import coroutineRunner

        task.setStatus(TaskStatus.RUNNING)
        workId = coroutineRunner.submit(
            task.run(),
            done=lambda _: self._onRunDone(task),
            failed=lambda error: self._onRunFailed(task, error),
        )
        self._queue.run(task.taskId, workId)
        if self._isPublishedTask(task):
            self.taskStarted.emit(task)

    def _cancelRun(self, task: Task, finished: Callable = None) -> None:
        from app.services.coroutine_runner import coroutineRunner

        workId = self._queue.workIdOf(task.taskId)
        self._queue.cancel(task.taskId)
        if workId is not None:
            coroutineRunner.cancel(workId, finished=finished)
        elif finished is not None:
            finished()

    def _rebalance(self) -> None:
        from app.models.task import TaskStatus
        for taskId in self._queue.runningIds()[cfg.maxTaskNum.value:]:
            task = self._taskById(taskId)
            if task is not None and task.canPause:
                self._cancelRun(task)
                task.setStatus(TaskStatus.WAITING)
                self._queue.wait(taskId)
        self._pump()

    def _pump(self) -> None:
        while self._queue.runningCount() < cfg.maxTaskNum.value:
            taskId = self._queue.nextWaiting()
            if taskId is None:
                break
            task = self._taskById(taskId)
            if task is not None:
                self._dispatch(task)

    def _onRunDone(self, task: Task) -> None:
        self._queue.done(task.taskId)
        if task.taskId in self._ignoredRunTaskIds:
            self._ignoredRunTaskIds.discard(task.taskId)
            self._pump()
            return
        isPublished = self._isPublishedTask(task)
        if isPublished:
            self._flushTimer.start()
            self.taskCompleted.emit(task)
            if task.hasOutputFile:
                self._watchFile(task)
        self._pump()
        if isPublished and not self._hasActivePublicTasks():
            self.tasksAllCompleted.emit()

    def _onRunFailed(self, task: Task, error: str) -> None:
        self._queue.done(task.taskId)
        if task.taskId in self._ignoredRunTaskIds:
            self._ignoredRunTaskIds.discard(task.taskId)
            if self._store.taskById(task.taskId) is task:
                self._schedule(task)
            else:
                self._pump()
            return
        isPublished = self._isPublishedTask(task)
        if isPublished:
            self._flushTimer.start()
            self.taskFailed.emit(task)
        self._pump()
        if isPublished and not self._hasActivePublicTasks():
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
        if Path(path).exists():
            return
        taskId = self._watchedPaths.pop(path, None)
        if taskId is None:
            return
        task = self._store.taskById(taskId)
        if task is not None:
            self.fileDisappeared.emit(task)


taskService = TaskService()
