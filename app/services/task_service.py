from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from loguru import logger

from app.config.cfg import cfg
from app.config.paths import APP_DATA_DIR

if TYPE_CHECKING:
    from app.models.task import Task


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
        self._waiting: list[Task] = []
        self._running: dict[Task, str] = {}

    def wait(self, task: Task) -> None:
        if task not in self._waiting:
            self._waiting.append(task)

    def removeWaiting(self, task: Task) -> None:
        if task in self._waiting:
            self._waiting.remove(task)

    def cancel(self, task: Task) -> None:
        self.removeWaiting(task)
        self._running.pop(task, None)

    def run(self, task: Task, workId: str) -> None:
        self._running[task] = workId

    def done(self, task: Task, workId: str) -> bool:
        if self._running.get(task) != workId:
            return False
        self._running.pop(task)
        return True

    def workIdOf(self, task: Task) -> str | None:
        return self._running.get(task)

    def isRunning(self, task: Task) -> bool:
        return task in self._running

    def isWaiting(self, task: Task) -> bool:
        return task in self._waiting

    def runningCount(self) -> int:
        return len(self._running)

    def runningTasks(self) -> list[Task]:
        return list(self._running)

    def nextWaiting(self) -> Task | None:
        return self._waiting.pop(0) if self._waiting else None


class TaskService(QObject):
    taskAdded = Signal(object)
    taskRemoved = Signal(str)
    taskStarted = Signal(object)
    taskPaused = Signal(object)
    taskCompleted = Signal(object)
    taskFailed = Signal(object)
    taskCancelled = Signal(object)
    tasksAllCompleted = Signal()
    fileDisappeared = Signal(object)
    diskSpaceInsufficient = Signal(int, int)

    def __init__(self, coroutineRunner, categoryService, speedMeter, parent=None):
        super().__init__(parent)
        self._coroutineRunner = coroutineRunner
        self._categoryService = categoryService
        self._speedMeter = speedMeter
        self._store = TaskStore()
        self._queue = TaskQueue()
        self._cancelVersions: dict[Task, int] = {}
        self._isStopping = False
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
        if task.taskId in self._store.tasks:
            return
        from app.models.task import TaskStatus

        isScheduled = self._queue.isRunning(task) or self._queue.isWaiting(task)
        if not isScheduled and task.status == TaskStatus.WAITING:
            if cfg.isCategoryEnabled.value:
                if task.category is None:
                    task.category = self._categoryService.categoryOf(task)
                if task.category and task.outputFolder == Path(cfg.downloadFolder.value):
                    folder = self._categoryService.folderOf(task.category)
                    if folder:
                        task.setOptions({"outputFolder": Path(folder)})
            task.deduplicateFilename()
        self._store.add(task)
        self._flushTimer.start()
        self.taskAdded.emit(task)
        if isScheduled:
            return
        if task.status == TaskStatus.COMPLETED:
            self.taskCompleted.emit(task)
            if task.hasOutputFile:
                self._watchFile(task)
            if self._queue.runningCount() == 0:
                self.tasksAllCompleted.emit()
            return
        if task.status == TaskStatus.FAILED:
            self.taskFailed.emit(task)
            return
        if task.fileSize > 0:
            from shutil import disk_usage
            try:
                free = disk_usage(task.outputFolder).free
                if free < task.fileSize:
                    self.diskSpaceInsufficient.emit(free, task.fileSize)
                    return
            except OSError:
                pass
        self._schedule(task)

    def start(self, task: Task) -> None:
        from app.models.task import TaskStatus
        if self._queue.isRunning(task):
            if task.status == TaskStatus.PAUSED:
                self._queue.wait(task)
            return
        if self._queue.isWaiting(task):
            return
        self._schedule(task)

    def pause(self, task: Task) -> None:
        from app.models.task import TaskStatus
        self._cancel(task)
        task.setStatus(TaskStatus.PAUSED)
        self._flushTimer.start()
        self.taskPaused.emit(task)

    def delete(self, task: Task, shouldDeleteFiles: bool) -> None:
        self._unwatchFile(task)
        self._cancel(task, finished=task.deleteFiles if shouldDeleteFiles else None)
        self._store.remove(task.taskId)
        self._flushTimer.start()
        self.taskRemoved.emit(task.taskId)

    def redownload(self, task: Task) -> None:
        self._unwatchFile(task)
        def afterStopped():
            task.deleteFiles()
            task.reset()
            self._flushTimer.start()
            self._schedule(task)
        self._cancel(task, finished=afterStopped)

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
        self._cancel(task, finished=afterStopped)

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
        if self._queue.isRunning(task):
            for step in task.steps:
                if step.status == TaskStatus.RUNNING:
                    fileIndex = step.fileIndex
                    isRunningDeselected = fileIndex is not None and fileIndex not in selectedSet
                    break

        if isRunningDeselected:
            def afterStopped():
                apply()
                self._schedule(task)
            self._cancel(task, finished=afterStopped)
            return
        apply()

    def startAll(self) -> None:
        from app.models.task import TaskStatus
        for task in self._store.tasks.values():
            if task.status in {TaskStatus.PAUSED, TaskStatus.WAITING, TaskStatus.FAILED}:
                self._schedule(task)

    def pauseAll(self) -> None:
        for task in list(self._store.tasks.values()):
            if self._queue.isRunning(task) or self._queue.isWaiting(task):
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
        self._isStopping = True
        for task in self._store.tasks.values():
            if task.status in {TaskStatus.RUNNING, TaskStatus.WAITING}:
                task.setStatus(TaskStatus.PAUSED)

    def flush(self) -> None:
        self._flushTimer.stop()
        self._store.flush()

    def _schedule(self, task: Task) -> None:
        self._queue.wait(task)
        self._pump()

    def _dispatch(self, task: Task) -> None:
        from app.models.task import TaskStatus

        task.setStatus(TaskStatus.RUNNING)
        workId = self._coroutineRunner.submit(
            task.run(self._speedMeter.addSpeed, self._speedMeter.waitForSpeedLimit),
            done=lambda _: self._onRunDone(task, workId),
            failed=lambda error: self._onRunFailed(task, workId, error),
        )
        self._queue.run(task, workId)
        if self._isStored(task):
            self.taskStarted.emit(task)
        else:
            self._speedMeter.start()

    def cancel(self, task: Task) -> None:
        self._cancel(task, finished=lambda: self.taskCancelled.emit(task))

    def _cancel(self, task: Task, finished: Callable = None) -> None:
        version = self._cancelVersions.get(task, 0) + 1
        self._cancelVersions[task] = version
        workId = self._queue.workIdOf(task)
        self._queue.removeWaiting(task)
        if workId is None:
            self._queue.cancel(task)
            if self._cancelVersions.pop(task, None) == version and finished is not None:
                finished()
            self._pump()
            return

        def afterStopped() -> None:
            isCurrent = self._queue.done(task, workId)
            try:
                isLatest = self._cancelVersions.get(task) == version
                if isLatest:
                    self._cancelVersions.pop(task)
                if isLatest and finished is not None:
                    finished()
            finally:
                if isCurrent:
                    self._pump()

        self._coroutineRunner.cancel(workId, finished=afterStopped)

    def _rebalance(self) -> None:
        from app.models.task import TaskStatus
        for task in self._queue.runningTasks()[cfg.maxTaskNum.value:]:
            if task.canPause:
                def setWaiting(task=task):
                    task.setStatus(TaskStatus.WAITING)
                    self._queue.wait(task)
                self._cancel(task, finished=setWaiting)
        self._pump()

    def _pump(self) -> None:
        if self._isStopping:
            return
        while self._queue.runningCount() < cfg.maxTaskNum.value:
            task = self._queue.nextWaiting()
            if task is None:
                break
            self._dispatch(task)

    def _onRunDone(self, task: Task, workId: str) -> None:
        if not self._queue.done(task, workId):
            return
        if self._isStored(task):
            self._flushTimer.start()
            self.taskCompleted.emit(task)
            if task.hasOutputFile:
                self._watchFile(task)
        self._pump()
        if self._queue.runningCount() == 0:
            self.tasksAllCompleted.emit()

    def _onRunFailed(self, task: Task, workId: str, error: str) -> None:
        if not self._queue.done(task, workId):
            return
        if self._isStored(task):
            self._flushTimer.start()
            self.taskFailed.emit(task)
        self._pump()
        if self._queue.runningCount() == 0:
            self.tasksAllCompleted.emit()

    def _isStored(self, task: Task) -> bool:
        return self._store.taskById(task.taskId) is task

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

