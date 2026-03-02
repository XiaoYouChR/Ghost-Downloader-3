import asyncio
import traceback
import sys
from typing import Callable, Dict, Any, Coroutine
from concurrent.futures import Future

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication
from loguru import logger

from app.bases.models import Task
from app.services.feature_service import featureService
from features.http_pack.pack import parse


class CoreService(QThread):
    """核心服务类，在子线程中运行独立的 AsyncIO 事件循环
    
    设计理念：
    1. 在 QThread 子线程中创建并运行独立的 asyncio 事件循环
    2. 提供线程安全的接口供主线程(Qt UI)调用
    3. 仅使用回调函数进行通知，避免 Qt Signal 的维护复杂性
    4. 通过 Qt 的线程安全机制确保 UI 更新的安全性
    5. 协调 FeatureService 进行 URL 解析和任务创建
    """

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.mainLoop = self.loop.create_task(self.main())
        self.tasks: set[Task] = set()
        self._pendingCallbacks: Dict[str, Callable[[dict, str | None], Coroutine | None]] = {}

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

            parseFunction = parse

            result = await parseFunction(payload)

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

    async def _createTask(self, payload: dict) -> Task:
        """内部异步方法：创建下载任务

        Args:
            payload: 包含任务创建信息的字典

        Returns:
            Task: 创建的任务对象
        """
        try:
            # TODO: 实现具体的任务创建逻辑
            # 这里应该调用 FeatureService 获取相应的任务创建函数
            # 然后执行任务创建流程

            # 示例实现
            task_data = {
                'title': payload.get('filename', '未知文件'),
                'metadata': {
                    'url': payload.get('url', ''),
                    'file_size': payload.get('fileSize', 0),
                    'download_path': payload.get('downloadPath', '')
                }
            }

            task = Task(**task_data)
            self.tasks.add(task)

            return task

        except Exception as e:
            errorMsg = f"创建任务失败: {str(e)}\n{traceback.format_exc()}"
            raise e

    async def _createTaskWithCallback(self, payload: dict, callbackId: str):
        """带回调的任务创建包装方法"""
        try:
            task = await self._createTask(payload)
            if callbackId in self._pendingCallbacks:
                callback = self._pendingCallbacks.pop(callbackId)
                self._executeCallback(callback, task, None)
        except Exception as e:
            errorMsg = f"创建任务失败: {str(e)}\n{traceback.format_exc()}"
            logger.exception(errorMsg)

            if callbackId in self._pendingCallbacks:
                callback = self._pendingCallbacks.pop(callbackId)
                self._executeCallback(callback, None, str(e))

    def createTask(self, payload: dict, callback: Callable) -> str:
        """线程安全的任务创建接口，使用回调函数
        
        Args:
            payload: 包含任务创建所需信息的字典
            callback: 回调函数，签名应为 callback(task: Task, error: str = None)
        
        Returns:
            str: 操作标识符
        """


        callbackId = f"create_{id(callback)}_{hash(str(payload))}"
        self._pendingCallbacks[callbackId] = callback
        self.loop.create_task(self._createTaskWithCallback(payload, callbackId))
        
        return callbackId

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