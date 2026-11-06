from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.cfg import cfg
from app.services.aria2_rpc import Aria2RpcService
from app.services.browser_service import BrowserService, CANDIDATE_PORTS
from app.services.category_service import CategoryService
from app.services.feature_service import FeatureService
from app.services.port_listener import PortListener
from app.services.name_conflict_queue import NameConflictQueue
from app.services.runtime_status import RuntimeStatusService
from app.services.speed_meter import SpeedMeter
from app.services.task_service import NameConflictChoice, TaskService

if TYPE_CHECKING:
    from PySide6.QtCore import QFileSystemWatcher
    from app.services.coroutine_runner import CoroutineRunner


class Engine:
    def __init__(
        self,
        coroutineRunner: CoroutineRunner,
        fileWatcher: QFileSystemWatcher,
        loadCrx: Callable[[], bytes],
        extensionFolder: Path,
        deleteRecoverably: Callable[[Path], bool],
    ) -> None:
        self.coroutineRunner = coroutineRunner
        self.categoryService = CategoryService()
        self.speedMeter = SpeedMeter(coroutineRunner)
        self.taskService = TaskService(coroutineRunner, self.categoryService, self.speedMeter, fileWatcher,
                                       deleteRecoverably, lambda: NameConflictChoice(cfg.nameConflict.value))
        self.nameConflictQueue = NameConflictQueue(self.taskService.probeConflict, self.taskService.add,
                                                   coroutineRunner.post)
        self.taskService.nameConflicted.connect(self.nameConflictQueue.add)
        self.runtimeStatusService = RuntimeStatusService(coroutineRunner)
        self.featureService = FeatureService(self.taskService, self.categoryService, coroutineRunner,
                                             self.runtimeStatusService)

        self.browserService = BrowserService(coroutineRunner, self.taskService, self.speedMeter.speedChanged,
                                             self.featureService.parse, loadCrx, extensionFolder)
        self.browserListener = PortListener(coroutineRunner, self.browserService.handle,
                                            isEnabled=cfg.isBrowserExtensionEnabled, port=cfg.browserExtensionPort,
                                            shouldAutoSelect=cfg.shouldAutoSelectBrowserPort,
                                            fallbackPorts=CANDIDATE_PORTS)
        self.aria2RpcService = Aria2RpcService(coroutineRunner, self.featureService.parse, self.taskService.add)
        self.aria2RpcListener = PortListener(coroutineRunner, self.aria2RpcService.handle,
                                             isEnabled=cfg.isAria2RpcEnabled, port=cfg.aria2RpcPort)

    def start(self) -> None:
        self.taskService.resumeSaved()
        self.featureService.activate()
        self.browserListener.start()
        self.aria2RpcListener.start()

    def stop(self) -> None:
        self.taskService.stop()
        self.taskService.flush()
        self.speedMeter.stop()
        self.browserListener.stop()
        self.aria2RpcListener.stop()
        self.featureService.deactivate()
        self.taskService.flush()
