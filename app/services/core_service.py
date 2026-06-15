import asyncio
import sys
from pathlib import Path
from typing import Callable, Dict, Any, Coroutine

from PySide6.QtCore import QThread, QTimer, QStandardPaths, QResource, QFileInfo, Qt
from PySide6.QtWidgets import QApplication, QFileIconProvider
from loguru import logger

from app.bases.models import Task, TaskStatus
from app.services.feature_service import featureService
from app.supports.android import IS_ANDROID
from app.supports.config import cfg
from app.supports.utils import openFile

# desktop-notifier 在 Android 无后端(靠 D-Bus)且无 wheel, 不打包; 完成通知留 v2 走 NotificationManager。
if not IS_ANDROID:
    from desktop_notifier import DesktopNotifier, Icon, Button

if sys.platform == 'win32':
    import winloop
    winloop.install()
elif sys.platform != 'darwin' and not IS_ANDROID:
    # Android 用 asyncio 默认事件循环(uvloop 无 Android 构建); 桌面 Linux 仍走 uvloop。
    import uvloop
    uvloop.install()

def getNotifierIcon() -> Path:
    _ = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation) + "/gd3_logo.png")
    if not _.exists():
        with open(_, "wb") as f:
            f.write(QResource(":/image/logo.png").data())
    return _

class CoreService(QThread):

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.mainLoop = self.loop.create_task(self.main())
        self.tasks: set[Task] = set()
        self.waitingTasks: list[Task] = []
        self.runningTasks: dict[str, asyncio.Task] = {}
        self._pendingCallbacks: Dict[str, Callable[[Any, str | None], Coroutine | None]] = {}
        cfg.maxTaskNum.valueChanged.connect(lambda _: self._rebalanceSoon())

    def sendNotification(self, task: Task):
        if IS_ANDROID:  # v1 无桌面通知后端, 静默
            return
        outputFolder = task.outputFolder
        if not outputFolder:
            logger.warning("task {} has no outputFolder for notification", task.taskId)
            return

        directoryPath = str(Path(outputFolder).parent)
        iconTempPath = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)) / "finished_file_icon.png"
        QFileIconProvider().icon(QFileInfo(outputFolder)).pixmap(48, 48).scaled(
            128,
            128,
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        ).save(str(iconTempPath), "PNG")
        buttons = [
            Button(self.tr('打开文件'), lambda: openFile(outputFolder)),
            Button(self.tr('打开目录'), lambda: openFile(directoryPath)),
        ]
        self.loop.create_task(
            self.desktopNotifier.send(
                self.tr("下载完成"),
                task.title,
                buttons=buttons,
                on_clicked=lambda: openFile(outputFolder),
                icon=Icon(path=iconTempPath),
            )
        )


    def runCoroutine(self, coroutine: Coroutine, callback: Callable[[Any, str | None], Coroutine | None] | None = None):
        if callback is not None:
            callbackId = f"custom_{id(callback)}_{hash(coroutine)}"

            self._pendingCallbacks[callbackId] = callback

            self.loop.create_task(self._runCoroutine(coroutine, callbackId))

            return callbackId

        return ""

    def runBlocking(self, coroutine: Coroutine, timeout: float | None = None):
        """从其它线程把协程丢到核心事件循环上跑并阻塞等结果(app 退出前收尾用)。"""
        if not self.loop.is_running():
            coroutine.close()
            return None
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)

    async def _runCoroutine(self, coroutine: Coroutine, callbackId):
        try:
            result = await coroutine
            error = None
        except Exception as e:
            logger.opt(exception=e).error("异步任务执行失败 {}", callbackId)
            result = None
            error = repr(e)

        callback = self._pendingCallbacks.pop(callbackId, None)
        if callback is not None:
            self._executeCallback(callback, result, error)

    def _executeCallback(self, callback: Callable, result: Any, error: str = None):
        """线程安全地执行回调函数

        通过 Qt 的事件循环机制确保回调在主线程中执行，
        避免子线程直接操作 UI 导致的崩溃问题。

        Args:
            callback: 回调函数
            result: 成功结果
            error: 错误信息
        """

        def wrapper():
            try:
                if asyncio.iscoroutinefunction(callback):
                    self.loop.create_task(callback(result, error))
                else:
                    callback(result, error)
            except Exception as e:
                logger.opt(exception=e).error("回调函数执行失败")

        application = QApplication.instance()
        if application:
            QTimer.singleShot(0, application, wrapper)
        else:
            wrapper()

    async def _parse(self, payload: dict):
        return await featureService.parse(payload)

    def _slotTaskIds(self) -> list[str]:
        taskIds: list[str] = []
        for taskId in self.runningTasks:
            task = self.task(taskId)
            if task is None or not task.usesSlot:
                continue
            taskIds.append(taskId)
        return taskIds

    def _removeWaitingTask(self, task: Task):
        self.waitingTasks = [queuedTask for queuedTask in self.waitingTasks if queuedTask.taskId != task.taskId]

    def _enqueueTask(self, task: Task):
        self._removeWaitingTask(task)
        task.setStatus(TaskStatus.WAITING)
        self.waitingTasks.append(task)

    def _dispatchTask(self, task: Task):
        self._removeWaitingTask(task)
        task.setStatus(TaskStatus.RUNNING)
        self.runningTasks[task.taskId] = self.loop.create_task(self._runTask(task))

    def _rebalanceSoon(self):
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(lambda: self.loop.create_task(self._rebalance()))

    def rebalance(self):
        self._rebalanceSoon()

    def _scheduleWaitingTasks(self):
        while self.waitingTasks and len(self._slotTaskIds()) < cfg.maxTaskNum.value:
            task = self.waitingTasks.pop(0)
            if task.taskId in self.runningTasks:
                continue

            self._dispatchTask(task)

    async def _requeueTask(self, task: Task):
        runningTask = self.runningTasks.get(task.taskId)
        if runningTask is None:
            self._enqueueTask(task)
            return

        if runningTask.cancel():
            try:
                await runningTask
            except asyncio.CancelledError:
                pass

        self.runningTasks.pop(task.taskId, None)

        if task.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            self._enqueueTask(task)

    async def _rebalance(self):
        runningTaskIds = self._slotTaskIds()
        overflowTaskIds = runningTaskIds[cfg.maxTaskNum.value:]

        for taskId in overflowTaskIds:
            task = self.task(taskId)
            if task is None:
                continue
            await self._requeueTask(task)

        self._scheduleWaitingTasks()

    async def _runTask(self, task: Task):
        try:
            await task.run()
        finally:
            self.runningTasks.pop(task.taskId, None)
            self._scheduleWaitingTasks()

    def createTask(self, task: Task):
        self.tasks.add(task)
        if task.taskId in self.runningTasks:
            return

        if task.usesSlot and len(self._slotTaskIds()) >= cfg.maxTaskNum.value:
            self._enqueueTask(task)
            return

        self._dispatchTask(task)

    async def _stopTask(self, task: Task):
        self.tasks.discard(task)
        self._removeWaitingTask(task)
        runningTask = self.runningTasks.get(task.taskId)
        if runningTask is not None and runningTask.cancel():
            try:
                await runningTask
            except asyncio.CancelledError:
                pass
        self.runningTasks.pop(task.taskId, None)
        self._scheduleWaitingTasks()

    def stopTask(self, task: Task):
        task.setStatus(TaskStatus.PAUSED)
        self.loop.create_task(self._stopTask(task))

    def task(self, taskId: str) -> Task | None:
        """根据任务Id获取任务对象

        Args:
            taskId: 任务Id

        Returns:
            Task: 对应的任务对象，如果不存在则返回None
        """
        for task in self.tasks:
            if task.taskId == taskId:
                return task
        return None

    def cancelCallback(self, callbackId: str) -> bool:
        """移除待执行的回调函数

        Args:
            callbackId: 回调函数标识符

        Returns:
            bool: 是否成功移除
        """
        if callbackId in self._pendingCallbacks:
            del self._pendingCallbacks[callbackId]
            return True
        return False

    async def main(self):
        """主事件循环

        在这里可以添加周期性任务，如清理过期回调、监控任务状态等
        """
        while True:
            try:
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.opt(exception=e).error("CoreService 主循环发生错误")
                await asyncio.sleep(1)

    def run(self):
        """启动线程和事件循环"""
        if not IS_ANDROID:
            self.desktopNotifier = DesktopNotifier(app_name="Ghost Downloader", app_icon=Icon(path=getNotifierIcon()))  # OSError: [WinError -2147417842] 应用程序调用一个已为另一线程整理的接口。
        try:
            self.loop.run_until_complete(self.mainLoop)
        except Exception as e:
            logger.opt(exception=e).error("CoreService 启动失败")
        finally:
            if self.loop:
                self.loop.close()

    def stop(self):
        """停止服务"""
        if self.loop and self.loop.is_running():
            if hasattr(self, 'mainLoop') and not self.mainLoop.done():
                self.mainLoop.cancel()

            self.loop.call_soon_threadsafe(self.loop.stop)

        self._pendingCallbacks.clear()
        self.tasks.clear()
        self.waitingTasks.clear()
        self.runningTasks.clear()
        cfg.maxTaskNum.valueChanged.disconnect()

coreService = CoreService()
