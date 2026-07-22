"""Shared engine startup, binding, and shutdown for desktop and Android."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.services.aria2_rpc import Aria2RpcServer
    from app.services.browser_service import BrowserService
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.feature_service import FeatureService
    from app.services.runtime_status import RuntimeStatusService
    from app.services.speed_meter import SpeedMeter
    from app.services.task_service import TaskService
    from app.update import Release
    from PySide6.QtWidgets import QApplication


def loadEngine(application: QApplication) -> tuple[CoroutineRunner, CategoryService, SpeedMeter]:
    from PySide6.QtCore import QTranslator
    from app.config.cfg import cfg
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.speed_meter import SpeedMeter

    import app.assets.resources  # noqa: F401

    locale = cfg.language.value.value
    translator = QTranslator(application)
    translator.load(locale, "gd3", ".", ":/i18n")
    application.installTranslator(translator)

    coroutineRunner = CoroutineRunner(parent=application)
    categoryService = CategoryService()
    speedMeter = SpeedMeter(parent=application)

    coroutineRunner.start()

    return coroutineRunner, categoryService, speedMeter


def createServices(
    coroutineRunner: CoroutineRunner,
    categoryService: CategoryService,
    speedMeter: SpeedMeter,
) -> tuple[FeatureService, TaskService, BrowserService, Aria2RpcServer, RuntimeStatusService]:
    from app.services.aria2_rpc import Aria2RpcServer
    from app.services.browser_service import BrowserService
    from app.services.feature_service import FeatureService
    from app.services.runtime_status import RuntimeStatusService
    from app.services.task_service import TaskService

    featureService = FeatureService()
    taskService = TaskService(coroutineRunner, categoryService, speedMeter)
    browserService = BrowserService(coroutineRunner, taskService, parse=featureService.parse)
    aria2RpcServer = Aria2RpcServer(coroutineRunner, parse=featureService.parse, addTask=taskService.add)
    runtimeStatusService = RuntimeStatusService(coroutineRunner)

    return featureService, taskService, browserService, aria2RpcServer, runtimeStatusService


def loadPacks(
    featureService: FeatureService,
    coroutineRunner: CoroutineRunner,
    speedMeter: SpeedMeter,
    taskService: TaskService,
    categoryService: CategoryService,
    runtimeStatusService: RuntimeStatusService,
) -> None:
    from app.models.pack import PackConfig, PackServices

    services = PackServices(
        coroutineRunner=coroutineRunner,
        speedMeter=speedMeter,
        taskService=taskService,
        featureService=featureService,
        categoryService=categoryService,
        runtimeStatusService=runtimeStatusService,
    )
    featureService.load(services)
    PackConfig.load()


def startEngine(
    taskService: TaskService,
    speedMeter: SpeedMeter,
    featureService: FeatureService,
    coroutineRunner: CoroutineRunner,
) -> None:
    taskService.taskStarted.connect(lambda _: speedMeter.start())
    taskService.tasksAllCompleted.connect(speedMeter.stop)
    taskService.resumeSaved()
    featureService.activate(coroutineRunner)


def bindNotifications(
    taskService: TaskService,
    notifyCompleted: Callable,
    notifyDiskSpace: Callable,
) -> None:
    taskService.taskCompleted.connect(notifyCompleted)
    taskService.diskSpaceInsufficient.connect(notifyDiskSpace)


def checkUpdateAtStartup(
    coroutineRunner: CoroutineRunner,
    onUpdateAvailable: Callable[[Release], None],
) -> None:
    from app.config.cfg import cfg
    if not cfg.shouldCheckUpdateAtStartup.value:
        return
    from app.update import fetchRelease, isOutdated

    def _onFetched(release: Release) -> None:
        if isOutdated(release):
            onUpdateAvailable(release)

    coroutineRunner.submit(fetchRelease(), done=_onFetched)


def stopEngine(
    taskService: TaskService,
    browserService: BrowserService,
    aria2RpcServer: Aria2RpcServer,
    featureService: FeatureService,
    coroutineRunner: CoroutineRunner,
) -> None:
    taskService.stop()
    taskService.flush()
    browserService.stop()
    aria2RpcServer.stop()
    featureService.deactivate(coroutineRunner)
    coroutineRunner.stop()
