"""Shared engine startup, binding, and shutdown for desktop and Android."""
from __future__ import annotations


def loadTranslators(application):
    from PySide6.QtCore import QTranslator
    from app.config.cfg import cfg

    translator = QTranslator(application)

    def setLocale():
        locale = cfg.language.value.value
        application.removeTranslator(translator)
        if locale.name() != "zh_CN":
            if translator.load(locale, "gd3", ".", ":/i18n") or translator.load("gd3.en_US", ":/i18n"):
                application.installTranslator(translator)

    setLocale()
    cfg.language.valueChanged.connect(setLocale)


def loadEngine(application):
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.speed_meter import SpeedMeter

    import app.assets.resources  # noqa: F401

    loadTranslators(application)

    coroutineRunner = CoroutineRunner(parent=application)
    categoryService = CategoryService()
    speedMeter = SpeedMeter(parent=application)

    coroutineRunner.start()

    return coroutineRunner, categoryService, speedMeter


def createServices(coroutineRunner, categoryService, speedMeter):
    from app.services.aria2_rpc import Aria2RpcServer
    from app.services.browser_service import BrowserService
    from app.services.feature_service import FeatureService
    from app.services.runtime_status import RuntimeStatusService
    from app.services.task_service import TaskService
    from app.services.update_service import UpdateService

    taskService = TaskService(coroutineRunner, categoryService, speedMeter)
    runtimeStatusService = RuntimeStatusService(coroutineRunner)
    featureService = FeatureService(taskService, categoryService, coroutineRunner, runtimeStatusService)
    browserService = BrowserService(coroutineRunner, taskService, parse=featureService.parse)
    aria2RpcServer = Aria2RpcServer(coroutineRunner, parse=featureService.parse, addTask=taskService.add)
    updateService = UpdateService(coroutineRunner)

    return featureService, taskService, browserService, aria2RpcServer, updateService, runtimeStatusService


def loadPacks(featureService, coroutineRunner, speedMeter):
    from app.models.pack import PackConfig, PackServices
    from app.services.update_service import installPendingPacks
    from app.config.paths import FEATURES_DIR, SEED_FEATURES_DIR
    from app.loader import seedPacks

    installPendingPacks(FEATURES_DIR)
    seedPacks(SEED_FEATURES_DIR, FEATURES_DIR)

    services = PackServices(
        coroutineRunner=coroutineRunner,
        speedMeter=speedMeter,
    )
    featureService.load(services)
    PackConfig.load()


def startEngine(taskService, speedMeter, featureService, coroutineRunner):
    taskService.taskStarted.connect(lambda _: speedMeter.start())
    taskService.tasksAllCompleted.connect(speedMeter.stop)
    taskService.resumeSaved()
    featureService.activate(coroutineRunner)


def bindNotifications(taskService, notifyCompleted, notifyDiskSpace):
    taskService.taskCompleted.connect(notifyCompleted)
    taskService.diskSpaceInsufficient.connect(notifyDiskSpace)


def checkUpdateAtStartup(updateService):
    from app.config.cfg import cfg
    from app.config.paths import IS_COMPILED, hasNoAutoUpdateMarker
    if hasNoAutoUpdateMarker():
        from loguru import logger
        logger.info("Auto update disabled by gd_no_auto_update marker")
        if cfg.shouldCheckUpdateAtStartup.value:
            cfg.set(cfg.shouldCheckUpdateAtStartup, False)
        return
    if not IS_COMPILED:
        return
    if not cfg.shouldCheckUpdateAtStartup.value:
        return
    updateService.check()


def stopEngine(taskService, browserService, aria2RpcServer, featureService, coroutineRunner, updateService=None):
    taskService.stop()
    taskService.flush()
    browserService.stop()
    aria2RpcServer.stop()
    featureService.deactivate(coroutineRunner)
    taskService.flush()
    if updateService is not None:
        updateService.apply()
    coroutineRunner.stop()
