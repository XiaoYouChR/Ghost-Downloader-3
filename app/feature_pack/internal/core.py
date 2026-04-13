# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportAny=false

"""Core task scheduling helpers for Feature Pack V1."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from collections.abc import Callable
from inspect import isawaitable
from typing import final
from typing import cast

from app.feature_pack.api import FeatureService
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput
from app.supports.config import cfg

from .recorder import TaskRecorder
from .recorder import taskRecorder


TaskLimitProvider = Callable[[], int]


def _currentTaskLimit(provider: TaskLimitProvider) -> int:
    limit = provider()
    if isinstance(limit, bool):
        return 1
    return max(1, int(limit))


def _taskState(task: Task) -> str:
    rawState = getattr(task, "state", None)
    if isinstance(rawState, str):
        return rawState.strip().lower()

    try:
        return task.snapshot().state.strip().lower()
    except Exception:
        return ""


def _emitTaskSnapshot(task: Task) -> None:
    try:
        task.snapshotChanged.emit(task.snapshot())
    except Exception:
        return None


def _setTaskState(task: Task, state: str) -> None:
    setState = getattr(task, "setState", None)
    if callable(setState):
        _ = setState(state)
        return

    setattr(task, "state", state)
    task.stateChanged.emit(state)
    _emitTaskSnapshot(task)


def _taskBoolHook(task: Task, hookName: str) -> bool | None:
    hook = getattr(task, hookName, None)
    if not callable(hook):
        return None
    return bool(hook())


def _occupiesDownloadSlot(task: Task) -> bool:
    occupiesSlot = _taskBoolHook(task, "occupiesDownloadSlot")
    if occupiesSlot is not None:
        return occupiesSlot
    return True


def _willOccupyDownloadSlotWhenStarted(task: Task) -> bool:
    occupiesSlot = _taskBoolHook(task, "willOccupyDownloadSlotWhenStarted")
    if occupiesSlot is not None:
        return occupiesSlot
    return _occupiesDownloadSlot(task)


@final
class FeaturePackCoreService:
    """Create, schedule, pause, and track Feature Pack V1 tasks."""

    featureService: FeatureService
    recorder: TaskRecorder | None
    tasksById: dict[str, Task]
    waitingTaskIds: list[str]
    runningTasks: dict[str, asyncio.Task[None]]
    taskErrors: dict[str, BaseException]

    def __init__(
        self,
        *,
        featureService: FeatureService,
        recorder: TaskRecorder | None = taskRecorder,
        maxRunningTasks: int | TaskLimitProvider | None = None,
    ) -> None:
        self.featureService = featureService
        self.recorder = recorder
        if callable(maxRunningTasks):
            self._maxRunningTasks = maxRunningTasks
        elif maxRunningTasks is None:
            self._maxRunningTasks = lambda: cast(int, cfg.maxTaskNum.value)
        else:
            fixedLimit = max(1, int(maxRunningTasks))
            self._maxRunningTasks = lambda fixedLimit=fixedLimit: fixedLimit

        self.tasksById = {}
        self.waitingTaskIds = []
        self.runningTasks = {}
        self.taskErrors = {}

    async def createTask(self, data: TaskInput) -> Task:
        task = await self.featureService.createTask(data)
        self.startTask(task)
        return task

    def startTask(self, task: Task) -> None:
        existingTask = self.tasksById.get(task.id)
        if existingTask is not None and existingTask is not task:
            raise ValueError(f"task {task.id} already exists")

        if existingTask is None:
            self.tasksById[task.id] = task
            self._rememberTask(task)

        if task.id in self.runningTasks or task.id in self.waitingTaskIds:
            return

        if (
            _willOccupyDownloadSlotWhenStarted(task)
            and self.runningTaskCount() >= self.maxRunningTasks()
        ):
            self._enqueueTask(task)
            self._flushRecorder()
            return

        self._dispatchTask(task)
        self._flushRecorder()

    async def stopTask(self, task: Task) -> None:
        self._removeWaitingTask(task)
        runningTask = self.runningTasks.get(task.id)

        if runningTask is not None:
            pause = getattr(task, "pause", None)
            if callable(pause):
                pauseResult = pause()
                if isawaitable(pauseResult):
                    _ = await cast(Awaitable[object], pauseResult)

            if runningTask.cancel():
                try:
                    await runningTask
                except asyncio.CancelledError:
                    pass

        _ = self.runningTasks.pop(task.id, None)
        if _taskState(task) not in {"completed", "failed"}:
            _setTaskState(task, "paused")

        self._flushRecorder()
        self._scheduleWaitingTasks()

    async def removeTask(self, task: Task) -> None:
        await self.stopTask(task)
        _ = self.tasksById.pop(task.id, None)
        _ = self.taskErrors.pop(task.id, None)

        if self.recorder is not None and task.id in self.recorder.memorizedTasks:
            _ = self.recorder.remove(task, flush=False)
        self._flushRecorder()

    def allTasks(self) -> list[Task]:
        return list(self.tasksById.values())

    def getTaskById(self, taskId: str) -> Task | None:
        return self.tasksById.get(taskId)

    def maxRunningTasks(self) -> int:
        return _currentTaskLimit(self._maxRunningTasks)

    def runningTaskCount(self) -> int:
        return len(self._downloadSlotTaskIds())

    def notifyTaskSchedulingChanged(self) -> asyncio.Task[None]:
        return asyncio.create_task(self.syncTaskLimit())

    async def syncTaskLimit(self) -> None:
        overflowTaskIds = self._downloadSlotTaskIds()[self.maxRunningTasks() :]
        for taskId in overflowTaskIds:
            task = self.tasksById.get(taskId)
            if task is None:
                continue
            await self._moveRunningTaskToWaiting(task)

        self._scheduleWaitingTasks()

    async def waitForIdle(self) -> None:
        while self.runningTasks or self.waitingTaskIds:
            currentRunningTasks = tuple(self.runningTasks.values())
            if currentRunningTasks:
                _ = await asyncio.gather(*currentRunningTasks, return_exceptions=True)
            else:
                self._scheduleWaitingTasks()
                await asyncio.sleep(0)

    def _rememberTask(self, task: Task) -> None:
        if self.recorder is None or task.id in self.recorder.memorizedTasks:
            return
        self.recorder.add(task, flush=False)

    def _flushRecorder(self) -> None:
        if self.recorder is None or not getattr(self.recorder, "_loaded", False):
            return
        self.recorder.flush()

    def _downloadSlotTaskIds(self) -> list[str]:
        taskIds: list[str] = []
        for taskId in self.runningTasks:
            task = self.tasksById.get(taskId)
            if task is None or not _occupiesDownloadSlot(task):
                continue
            taskIds.append(taskId)
        return taskIds

    def _removeWaitingTask(self, task: Task) -> None:
        self.waitingTaskIds = [
            queuedTaskId
            for queuedTaskId in self.waitingTaskIds
            if queuedTaskId != task.id
        ]

    def _enqueueTask(self, task: Task) -> None:
        self._removeWaitingTask(task)
        _setTaskState(task, "waiting")
        self.waitingTaskIds.append(task.id)

    def _dispatchTask(self, task: Task) -> None:
        self._removeWaitingTask(task)
        _setTaskState(task, "running")
        self.runningTasks[task.id] = asyncio.create_task(
            self._runTask(task),
            name=f"feature_pack_task:{task.id}",
        )

    async def _moveRunningTaskToWaiting(self, task: Task) -> None:
        runningTask = self.runningTasks.get(task.id)
        if runningTask is None:
            self._enqueueTask(task)
            return

        if runningTask.cancel():
            try:
                await runningTask
            except asyncio.CancelledError:
                pass

        _ = self.runningTasks.pop(task.id, None)
        if _taskState(task) not in {"completed", "failed"}:
            self._enqueueTask(task)

    def _scheduleWaitingTasks(self) -> None:
        while self.waitingTaskIds and self.runningTaskCount() < self.maxRunningTasks():
            taskId = self.waitingTaskIds.pop(0)
            task = self.tasksById.get(taskId)
            if task is None or task.id in self.runningTasks:
                continue
            self._dispatchTask(task)

    async def _runTask(self, task: Task) -> None:
        currentAsyncTask = asyncio.current_task()

        try:
            await task.run()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.taskErrors[task.id] = error
            if _taskState(task) not in {"completed", "failed"}:
                _setTaskState(task, "failed")
        else:
            if _taskState(task) not in {"completed", "failed"}:
                _setTaskState(task, "completed")
        finally:
            if self.runningTasks.get(task.id) is currentAsyncTask:
                _ = self.runningTasks.pop(task.id, None)

            self._flushRecorder()
            self._scheduleWaitingTasks()


__all__ = ["FeaturePackCoreService"]
