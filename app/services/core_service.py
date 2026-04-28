# pyright: reportImportCycles=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false, reportAny=false, reportExplicitAny=false, reportMissingParameterType=false, reportUnannotatedClassAttribute=false, reportUninitializedInstanceVariable=false, reportArgumentType=false, reportImplicitOverride=false, reportDeprecated=false, reportUnusedCallResult=false

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from typing import cast

from PySide6.QtCore import QFileInfo
from PySide6.QtCore import QResource
from PySide6.QtCore import QStandardPaths
from PySide6.QtCore import QThread
from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QFileIconProvider
from desktop_notifier import Button
from desktop_notifier import DesktopNotifier
from desktop_notifier import Icon
from loguru import logger

from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput
from app.services.feature_service import featureService
from app.supports.config import cfg
from app.supports.utils import openFile

if sys.platform == "win32":
    import winloop

    winloop.install()
elif sys.platform != "darwin":
    import uvloop

    uvloop.install()


TaskCallback = Callable[[Task | None, str | None], Coroutine[Any, Any, None] | None]
CoroutineCallback = Callable[[Any, str | None], Coroutine[Any, Any, None] | None]


def getNotifierIcon() -> Path:
    iconPath = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
        + "/gd3_logo.png"
    )
    if not iconPath.exists():
        with open(iconPath, "wb") as file:
            file.write(cast(bytes, QResource(":/image/logo.png").data()))
    return iconPath


def _taskId(task: Task) -> str:
    return task.id


def _taskState(task: Task) -> str:
    try:
        return task.snapshot().state.strip().lower()
    except Exception:
        rawState = getattr(task, "state", "")
        return rawState.strip().lower() if isinstance(rawState, str) else ""


def _taskTarget(task: Task) -> str:
    try:
        return task.snapshot().target.strip()
    except Exception:
        rawTarget = getattr(task, "resolvePath", "")
        return rawTarget.strip() if isinstance(rawTarget, str) else ""


def _taskName(task: Task) -> str:
    try:
        return task.snapshot().name
    except Exception:
        rawTitle = getattr(task, "title", "")
        return rawTitle if isinstance(rawTitle, str) else task.id


def _setTaskState(task: Task, state: str) -> None:
    setState = getattr(task, "setState", None)
    if callable(setState):
        _ = setState(state)
        return

    setattr(task, "state", state)
    task.stateChanged.emit(state)
    try:
        task.snapshotChanged.emit(task.snapshot())
    except Exception:
        return


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


class CoreService(QThread):
    def __init__(self) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.mainLoop = self.loop.create_task(self.main())
        self.tasksById: dict[str, Task] = {}
        self.waitingTaskIds: list[str] = []
        self.runningTasks: dict[str, asyncio.Task[None]] = {}
        self._pendingCallbacks: dict[str, CoroutineCallback] = {}
        cfg.maxTaskNum.valueChanged.connect(lambda _: self._syncTaskLimitSoon())

    def sendNotification(self, task: Task) -> None:
        resolvePath = _taskTarget(task)
        if not resolvePath:
            logger.warning("task {} has no target for notification", task.id)
            return

        directoryPath = str(Path(resolvePath).parent)
        iconTempPath = (
            Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation))
            / "finished_file_icon.png"
        )
        QFileIconProvider().icon(QFileInfo(resolvePath)).pixmap(48, 48).scaled(
            128,
            128,
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        ).save(str(iconTempPath), "PNG")
        buttons = [
            Button(self.tr("打开文件"), lambda: openFile(resolvePath)),
            Button(self.tr("打开目录"), lambda: openFile(directoryPath)),
        ]
        self.loop.create_task(
            self.desktopNotifier.send(
                self.tr("下载完成"),
                _taskName(task),
                buttons=buttons,
                on_clicked=lambda: openFile(resolvePath),
                icon=Icon(path=iconTempPath),
            )
        )

    def runCoroutine(
        self,
        coroutine: Coroutine[Any, Any, Any],
        callback: CoroutineCallback | None = None,
    ) -> str:
        if callback is None:
            self.loop.create_task(coroutine)
            return ""

        callbackId = f"custom_{id(callback)}_{hash(coroutine)}"
        self._pendingCallbacks[callbackId] = callback
        self.loop.create_task(self._runCoroutine(coroutine, callbackId))
        return callbackId

    async def _runCoroutine(
        self,
        coroutine: Coroutine[Any, Any, Any],
        callbackId: str,
    ) -> None:
        try:
            result = await coroutine
            callback = self._pendingCallbacks.pop(callbackId, None)
            if callback is not None:
                self._executeCallback(callback, result, None)
        except Exception as error:
            logger.opt(exception=error).error("异步任务执行失败 {}", callbackId)
            callback = self._pendingCallbacks.pop(callbackId, None)
            if callback is not None:
                self._executeCallback(callback, None, repr(error))

    def _executeCallback(
        self,
        callback: CoroutineCallback,
        result: Any,
        error: str | None = None,
    ) -> None:
        def wrapper() -> None:
            try:
                if asyncio.iscoroutinefunction(callback):
                    self.loop.create_task(callback(result, error))
                else:
                    callback(result, error)
            except Exception as callbackError:
                logger.opt(exception=callbackError).error("回调函数执行失败")

        application = QApplication.instance()
        if application:
            QTimer.singleShot(0, application, wrapper)
        else:
            wrapper()

    async def _createTaskFromInput(self, data: TaskInput) -> Task:
        return await featureService.createTask(data)

    def createTaskFromInput(self, data: TaskInput, callback: TaskCallback) -> str:
        callbackId = f"create_{id(callback)}_{hash(data.config.source)}"
        self._pendingCallbacks[callbackId] = callback
        self.loop.create_task(self._runCoroutine(self._createTaskFromInput(data), callbackId))
        return callbackId

    def _downloadSlotTaskIds(self) -> list[str]:
        taskIds: list[str] = []
        for taskId in self.runningTasks:
            task = self.getTaskById(taskId)
            if task is None or not _occupiesDownloadSlot(task):
                continue
            taskIds.append(taskId)
        return taskIds

    def _runningTaskCount(self) -> int:
        return len(self._downloadSlotTaskIds())

    def _removeWaitingTask(self, task: Task) -> None:
        taskId = _taskId(task)
        self.waitingTaskIds = [
            queuedTaskId
            for queuedTaskId in self.waitingTaskIds
            if queuedTaskId != taskId
        ]

    def _enqueueTask(self, task: Task) -> None:
        self._removeWaitingTask(task)
        _setTaskState(task, "waiting")
        self.waitingTaskIds.append(_taskId(task))

    def _dispatchTask(self, task: Task) -> None:
        taskId = _taskId(task)
        self._removeWaitingTask(task)
        _setTaskState(task, "running")
        self.runningTasks[taskId] = self.loop.create_task(self._runTask(task))

    def _syncTaskLimitSoon(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(lambda: self.loop.create_task(self._syncTaskLimit()))

    def notifyTaskSchedulingChanged(self) -> None:
        self._syncTaskLimitSoon()

    def _scheduleWaitingTasks(self) -> None:
        while self.waitingTaskIds and self._runningTaskCount() < cfg.maxTaskNum.value:
            taskId = self.waitingTaskIds.pop(0)
            task = self.tasksById.get(taskId)
            if task is None or taskId in self.runningTasks:
                continue
            self._dispatchTask(task)

    async def _moveRunningTaskToWaiting(self, task: Task) -> None:
        taskId = _taskId(task)
        runningTask = self.runningTasks.get(taskId)
        if runningTask is None:
            self._enqueueTask(task)
            return

        if runningTask.cancel():
            try:
                await runningTask
            except asyncio.CancelledError:
                pass

        self.runningTasks.pop(taskId, None)
        if _taskState(task) not in {"completed", "failed"}:
            self._enqueueTask(task)

    async def _syncTaskLimit(self) -> None:
        runningTaskIds = self._downloadSlotTaskIds()
        overflowTaskIds = runningTaskIds[cfg.maxTaskNum.value :]

        for taskId in overflowTaskIds:
            task = self.getTaskById(taskId)
            if task is None:
                continue
            await self._moveRunningTaskToWaiting(task)

        self._scheduleWaitingTasks()

    async def _runTask(self, task: Task) -> None:
        taskId = _taskId(task)
        try:
            await task.run()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.opt(exception=error).error("任务运行失败 {}", taskId)
            if _taskState(task) not in {"completed", "failed"}:
                _setTaskState(task, "failed")
        else:
            if _taskState(task) not in {"completed", "failed"}:
                _setTaskState(task, "completed")
        finally:
            self.runningTasks.pop(taskId, None)
            self._scheduleWaitingTasks()

    def createTask(self, task: Task) -> None:
        taskId = _taskId(task)
        existingTask = self.tasksById.get(taskId)
        if existingTask is not None and existingTask is not task:
            raise ValueError(f"task {taskId} already exists")

        self.tasksById[taskId] = task
        if taskId in self.runningTasks:
            return

        if (
            _willOccupyDownloadSlotWhenStarted(task)
            and self._runningTaskCount() >= cfg.maxTaskNum.value
        ):
            self._enqueueTask(task)
            return

        self._dispatchTask(task)

    async def _stopTask(self, task: Task) -> None:
        taskId = _taskId(task)
        self._removeWaitingTask(task)
        runningTask = self.runningTasks.get(taskId)
        if runningTask is not None:
            try:
                await task.pause()
            except Exception as error:
                logger.opt(exception=error).warning("任务暂停命令失败 {}", taskId)

            if runningTask.cancel():
                try:
                    await runningTask
                except asyncio.CancelledError:
                    pass

        self.runningTasks.pop(taskId, None)
        if _taskState(task) not in {"completed", "failed"}:
            _setTaskState(task, "paused")
        self._scheduleWaitingTasks()

    def stopTask(self, task: Task) -> None:
        self.loop.create_task(self._stopTask(task))

    def getAllTaskInfo(self) -> set[Task]:
        return set(self.tasksById.values())

    def getTaskById(self, taskId: str) -> Task | None:
        return self.tasksById.get(taskId)

    def removeCallback(self, callbackId: str) -> bool:
        if callbackId in self._pendingCallbacks:
            del self._pendingCallbacks[callbackId]
            return True
        return False

    async def main(self) -> None:
        while True:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as error:
                logger.opt(exception=error).error("CoreService 主循环发生错误")
                await asyncio.sleep(1)

    def run(self) -> None:
        self.desktopNotifier = DesktopNotifier(
            app_name="Ghost Downloader",
            app_icon=Icon(path=getNotifierIcon()),
        )
        try:
            self.loop.run_until_complete(self.mainLoop)
        except Exception as error:
            logger.opt(exception=error).error("CoreService 启动失败")
        finally:
            if self.loop:
                self.loop.close()

    def stop(self) -> None:
        if self.loop and self.loop.is_running():
            if hasattr(self, "mainLoop") and not self.mainLoop.done():
                self.mainLoop.cancel()

            self.loop.call_soon_threadsafe(self.loop.stop)

        self._pendingCallbacks.clear()
        self.tasksById.clear()
        self.waitingTaskIds.clear()
        self.runningTasks.clear()
        cfg.maxTaskNum.valueChanged.disconnect()


coreService = CoreService()
