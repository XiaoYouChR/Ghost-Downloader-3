"""桌面和 Android 共用的服务图与启停顺序。平台差异在构造时注入。"""
from __future__ import annotations

from app.config.cfg import cfg
from app.services.aria2_rpc import Aria2RpcService
from app.services.browser_service import BrowserService
from app.services.category_service import CategoryService
from app.services.feature_service import FeatureService
from app.services.loopback_server import LoopbackServer
from app.services.runtime_status import RuntimeStatusService
from app.services.speed_meter import SpeedMeter
from app.services.task_service import TaskService


class Engine:
    """不发信号、不持有 View；View 直接连接各服务的信号。coroutineRunner 由组合根创建并启停。"""

    def __init__(self, coroutineRunner, fileWatcher, loadCrx) -> None:
        self.coroutineRunner = coroutineRunner
        self.categoryService = CategoryService()
        self.speedMeter = SpeedMeter(coroutineRunner)
        self.taskService = TaskService(coroutineRunner, self.categoryService, self.speedMeter, fileWatcher)
        self.runtimeStatusService = RuntimeStatusService(coroutineRunner)
        self.featureService = FeatureService(self.taskService, self.categoryService, coroutineRunner,
                                             self.runtimeStatusService)

        self.browserService = BrowserService(coroutineRunner, self.taskService, self.featureService.parse, loadCrx)
        self.browserServer = LoopbackServer(coroutineRunner, self.browserService.handle,
                                            isEnabled=cfg.isBrowserExtensionEnabled, port=cfg.browserExtensionPort)
        self.aria2RpcService = Aria2RpcService(coroutineRunner, self.featureService.parse, self.taskService.add)
        self.aria2RpcServer = LoopbackServer(coroutineRunner, self.aria2RpcService.handle,
                                             isEnabled=cfg.isAria2RpcEnabled, port=cfg.aria2RpcPort)

    def start(self) -> None:
        self.taskService.resumeSaved()
        self.featureService.activate()
        self.browserServer.start()
        self.aria2RpcServer.start()

    def stop(self) -> None:
        self.taskService.stop()
        self.taskService.flush()
        self.speedMeter.stop()
        self.browserServer.stop()
        self.aria2RpcServer.stop()
        self.featureService.deactivate()
        self.taskService.flush()
