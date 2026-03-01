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
        self._pending_callbacks: Dict[str, Callable] = {}  # 存储待执行的回调函数

    def runCoroutine(self, coroutine: Coroutine, callback):
        # 生成回调标识符
        callback_id = f"custom_{id(callback)}_{hash(str(coroutine))}"

        # 存储回调函数
        self._pending_callbacks[callback_id] = callback

        self.loop.create_task(self._runCoroutine(coroutine, callback_id))

        return callback_id

    async def _runCoroutine(self, coroutine: Coroutine, callback_id):
        try:
            result = await coroutine
            callback = self._pending_callbacks.pop(callback_id)
            self._executeCallback(callback, result, None)
        except Exception as e:
            callback = self._pending_callbacks.pop(callback_id)
            self._executeCallback(callback, None, repr(e))

    async def _parseUrl(self, payload: dict, callback_id: str = None):
        """内部异步方法：解析 URL 并通过线程安全方式调用回调

        Args:
            payload: 包含 url, headers, proxies 等信息的字典
            callback_id: 回调函数标识符
        """
        try:
            url = payload.get('url', '')
            if not url:
                raise ValueError("URL 不能为空")
            
            # 从 FeatureService 获取对应的解析函数
            parse_function = featureService.getParseFunction(url)
            if parse_function is None:
                raise ValueError(f"不支持的 URL 类型: {url}")
            
            # 执行解析
            result = await parse_function(payload)
            
            # 通过线程安全方式调用回调
            if callback_id and callback_id in self._pending_callbacks:
                callback = self._pending_callbacks.pop(callback_id)
                self._executeCallback(callback, result, None)
                
        except Exception as e:
            error_msg = f"解析 URL 失败: {str(e)}\n{traceback.format_exc()}"
            # 在子线程中打印错误信息到终端
            logger.exception(error_msg)
            
            if callback_id and callback_id in self._pending_callbacks:
                callback = self._pending_callbacks.pop(callback_id)
                self._executeCallback(callback, None, error_msg)

    def parseUrl(self, payload: dict, callback: Callable = None) -> str:
        """线程安全的 URL 解析接口，仅使用回调函数
        
        Args:
            payload: 包含解析所需信息的字典
                    必须包含: url (str)
                    可选包含: headers (dict), proxies (dict)
            callback: 回调函数，签名应为 callback(result: dict, error: str = None)
        
        Returns:
            str: 操作标识符，可用于追踪该解析请求
        """
        if not self.loop or not self.loop.is_running():
            raise RuntimeError("CoreService 事件循环未运行")
        
        if callback is None:
            raise ValueError("必须提供回调函数")
        
        # 生成回调标识符
        callback_id = f"parse_{id(callback)}_{hash(str(payload))}"
        
        # 存储回调函数
        self._pending_callbacks[callback_id] = callback
        
        # 在事件循环中调度解析任务
        self.loop.create_task(self._parseUrl(payload, callback_id))
        
        return callback_id

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
            error_msg = f"创建任务失败: {str(e)}\n{traceback.format_exc()}"
            raise

    def createTask(self, payload: dict, callback: Callable = None) -> str:
        """线程安全的任务创建接口，使用回调函数
        
        Args:
            payload: 包含任务创建所需信息的字典
            callback: 回调函数，签名应为 callback(task: Task, error: str = None)
        
        Returns:
            str: 操作标识符
        """
        if not self.loop or not self.loop.is_running():
            raise RuntimeError("CoreService 事件循环未运行")
        
        if callback is None:
            raise ValueError("必须提供回调函数")
        
        # 生成回调标识符
        callback_id = f"create_{id(callback)}_{hash(str(payload))}"
        
        # 存储回调函数
        self._pending_callbacks[callback_id] = callback
        
        # 在事件循环中调度任务创建
        self.loop.create_task(self._createTaskWithCallback(payload, callback_id))
        
        return callback_id
    
    async def _createTaskWithCallback(self, payload: dict, callback_id: str):
        """带回调的任务创建包装方法"""
        try:
            task = await self._createTask(payload)
            if callback_id in self._pending_callbacks:
                callback = self._pending_callbacks.pop(callback_id)
                self._executeCallback(callback, task, None)
        except Exception as e:
            error_msg = f"创建任务失败: {str(e)}\n{traceback.format_exc()}"
            # 在子线程中打印错误信息到终端
            logger.exception(error_msg)
            
            if callback_id in self._pending_callbacks:
                callback = self._pending_callbacks.pop(callback_id)
                self._executeCallback(callback, None, str(e))

    def getAllTaskInfo(self) -> set:
        """获取所有任务信息
        
        Returns:
            set: 所有任务对象的集合
        """
        return self.tasks.copy()
    
    def getTaskById(self, task_id: str) -> Task:
        """根据任务ID获取任务对象
        
        Args:
            task_id: 任务ID
        
        Returns:
            Task: 对应的任务对象，如果不存在则返回None
        """
        for task in self.tasks:
            if task.taskId == task_id:
                return task
        return None
    
    def removeCallback(self, callback_id: str) -> bool:
        """移除待执行的回调函数
        
        Args:
            callback_id: 回调函数标识符
        
        Returns:
            bool: 是否成功移除
        """
        if callback_id in self._pending_callbacks:
            del self._pending_callbacks[callback_id]
            return True
        return False
    
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
                    # 如果是协程函数，在事件循环中执行
                    self.loop.create_task(callback(result, error))
                else:
                    # 普通函数直接调用
                    callback(result, error)
            except Exception as e:
                errorMsg = f"回调函数执行失败: {str(e)}\n{traceback.format_exc()}"
                logger.exception(errorMsg)

        if QApplication.instance():
            QTimer.singleShot(0, QApplication.instance(), wrapper)
        else:
            wrapper()

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
                # 优雅退出
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
            # 取消主循环任务
            if hasattr(self, 'mainLoop') and not self.mainLoop.done():
                self.mainLoop.cancel()
            
            # 关闭事件循环
            self.loop.call_soon_threadsafe(self.loop.stop)

    # def isRunning(self) -> bool:
    #     """检查服务是否正在运行
    #
    #     Returns:
    #         bool: 服务运行状态
    #     """
    #     return self.loop is not None and self.loop.is_running()

coreService = CoreService()
