import asyncio
import traceback
from pathlib import Path
from typing import Callable, Dict, Any, Coroutine

from PySide6.QtCore import QThread, QTimer, QStandardPaths, QResource, QFileInfo, Qt
from PySide6.QtWidgets import QApplication, QFileIconProvider
from desktop_notifier import DesktopNotifier, Icon, Button
from loguru import logger

from app.bases.models import Task, TaskStatus
from app.services.feature_service import featureService
from app.supports.utils import openFile


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
        self.runningTasks: dict[str, asyncio.Task] = {}
        self._pendingCallbacks: Dict[str, Callable[[dict, str | None], Coroutine | None]] = {}
        self.desktopNotifier = DesktopNotifier(app_name="Ghost Downloader", app_icon=Icon(path=getNotifierIcon()))

    def sendNotification(self, task: Task):
        resolvePath = task.resolvePath
        if not resolvePath:
            logger.error(f"task {task.taskId} has no resolvePath for notification")
            return

        directoryPath = str(Path(resolvePath).parent)
        iconTempPath = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)) / "finished_file_icon.png"
        QFileIconProvider().icon(QFileInfo(resolvePath)).pixmap(48, 48).scaled(
            128,
            128,
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        ).save(str(iconTempPath), "PNG")
        buttons = [
            Button(self.tr('打开文件'), lambda: openFile(resolvePath)),
            Button(self.tr('打开目录'), lambda: openFile(directoryPath)),
        ]
        self.loop.create_task(
            self.desktopNotifier.send(
                self.tr("下载完成"),
                task.title,
                buttons=buttons,
                on_clicked=lambda: openFile(resolvePath),
                icon=Icon(path=iconTempPath),
            )
        )


    def runCoroutine(self, coroutine: Coroutine, callback: Callable[[dict, str | None], Coroutine | None] | None = None):
        if callback is not None:
            callbackId = f"custom_{id(callback)}_{hash(coroutine)}"

            self._pendingCallbacks[callbackId] = callback

            self.loop.create_task(self._runCoroutine(coroutine, callbackId))

            return callbackId

        return ""

    async def _runCoroutine(self, coroutine: Coroutine, callbackId):
        try:
            result = await coroutine
            callback = self._pendingCallbacks.pop(callbackId)
            self._executeCallback(callback, result, None)
        except Exception as e:
            callback = self._pendingCallbacks.pop(callbackId)
            self._executeCallback(callback, None, repr(e))

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
                errorMsg = f"回调函数执行失败: {str(e)}\n{traceback.format_exc()}"
                logger.exception(errorMsg)

        application = QApplication.instance()
        if application:
            QTimer.singleShot(0, application, wrapper)
        else:
            wrapper()

    async def _parseUrl(self, payload: dict, callbackId: str = None):
        """内部异步方法：解析 URL 并通过线程安全方式调用回调

        Args:
            payload: 包含 url, headers, proxies 等信息的字典
            callbackId: 回调函数标识符
        """
        try:
            url = payload.get('url', '')
            if not url:
                raise ValueError("URL 不能为空")

            result = await featureService.parse(payload)

            if callbackId and callbackId in self._pendingCallbacks:
                callback = self._pendingCallbacks.pop(callbackId)
                self._executeCallback(callback, result, None)

        except Exception as e:
            errorMsg = f"解析 URL 失败: {str(e)}\n{traceback.format_exc()}"
            logger.exception(errorMsg)

            if callbackId and callbackId in self._pendingCallbacks:
                callback = self._pendingCallbacks.pop(callbackId)
                self._executeCallback(callback, None, errorMsg)

    def parseUrl(self, payload: dict, callback: Callable) -> str:
        callbackId = f"parse_{id(callback)}_{hash(str(payload))}"
        self._pendingCallbacks[callbackId] = callback

        self.loop.create_task(self._parseUrl(payload, callbackId))

        return callbackId

    async def _runTask(self, task: Task):
        self.runningTasks[task.taskId] = asyncio.create_task(task.run())

    def createTask(self, task: Task):
        self.tasks.add(task)
        task.setStatus(TaskStatus.RUNNING)
        self.loop.create_task(self._runTask(task))

    async def _stopTask(self, task: Task):
        self.tasks.discard(task)
        runningTask = self.runningTasks.pop(task.taskId, None)
        if runningTask is not None and runningTask.cancel():
            try:
                await runningTask
            except asyncio.CancelledError:
                pass

    def stopTask(self, task: Task):
        task.setStatus(TaskStatus.PAUSED)
        self.loop.create_task(self._stopTask(task))

    def getAllTaskInfo(self) -> set:
        """获取所有任务信息
        
        Returns:
            set: 所有任务对象的集合
        """
        return self.tasks.copy()
    
    def getTaskById(self, taskId: str) -> Task | None:
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
    
    def removeCallback(self, callbackId: str) -> bool:
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
                # 清理过期的回调函数（超过一定时间未执行的）
                # TODO: 实现回调清理逻辑
                
                # 监控任务状态
                # TODO: 实现任务状态监控逻辑
                
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"主循环发生错误: {e}")
                await asyncio.sleep(1)

    def run(self):
        """启动线程和事件循环"""
        try:
            self.loop.run_until_complete(self.mainLoop)
        except Exception as e:
            print(f"CoreService 启动失败: {e}")
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

coreService = CoreService()

# TODO 程序现在无法正常退出 何意味?
