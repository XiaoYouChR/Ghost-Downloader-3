"""Shared engine startup, binding, and shutdown for desktop and Android."""
from __future__ import annotations


def loadTranslators(application):
    from PySide6.QtCore import QLocale, QTranslator
    from app.config.cfg import cfg

    translator = QTranslator(application)

    def setLocale():
        localeName = cfg.language.value.value
        locale = QLocale() if localeName == "Auto" else QLocale(localeName)
        application.removeTranslator(translator)
        if locale.name() != "zh_CN":
            if translator.load(locale, "gd3", ".", ":/i18n") or translator.load("gd3.en_US", ":/i18n"):
                application.installTranslator(translator)

    setLocale()
    cfg.language.valueChanged.connect(setLocale)


def loadEngine(application):
    import sys
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.speed_meter import SpeedMeter

    from PySide6.QtCore import QResource, QTimer
    from shiboken6 import isValid
    from app.config.paths import executableDir

    QResource.registerResource(str(executableDir / "app" / "assets" / "resources.rcc"))

    loadTranslators(application)

    if sys.platform == "win32":
        from winloop import new_event_loop
    else:
        from uvloop import new_event_loop

    coroutineRunner = CoroutineRunner(
        lambda fn: QTimer.singleShot(0, application, fn), isAlive=isValid,
        loop=new_event_loop(),
    )
    categoryService = CategoryService()
    speedMeter = SpeedMeter(coroutineRunner)

    coroutineRunner.start()

    return coroutineRunner, categoryService, speedMeter


def createServices(coroutineRunner, categoryService, speedMeter):
    from PySide6.QtCore import QFileSystemWatcher
    from app.services.aria2_rpc import Aria2RpcServer
    from app.services.browser_service import BrowserService
    from app.services.feature_service import FeatureService
    from app.services.runtime_status import RuntimeStatusService
    from app.services.task_service import TaskService
    from app.services.update_service import UpdateService

    fileWatcher = QFileSystemWatcher()
    taskService = TaskService(coroutineRunner, categoryService, speedMeter, fileWatcher)
    runtimeStatusService = RuntimeStatusService(coroutineRunner)
    featureService = FeatureService(taskService, categoryService, coroutineRunner, runtimeStatusService)
    def loadCrx():
        from PySide6.QtCore import QResource
        return bytes(QResource(":/res/chrome_extension.crx").data())

    browserService = BrowserService(coroutineRunner, taskService, parse=featureService.parse, loadCrx=loadCrx)
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
    featureService.activate()


def bindNotifications(taskService, notifyCompleted, notifyDiskSpace):
    taskService.taskCompleted.connect(notifyCompleted)
    taskService.diskSpaceInsufficient.connect(notifyDiskSpace)


def checkUpdateAtStartup(updateService):
    from app.config.cfg import cfg
    if not cfg.shouldCheckUpdateAtStartup.value:
        return
    updateService.check()


def stopEngine(taskService, browserService, aria2RpcServer, featureService, coroutineRunner, speedMeter, updateService=None):
    taskService.stop()
    taskService.flush()
    speedMeter.stop()
    browserService.stop()
    aria2RpcServer.stop()
    featureService.deactivate()
    taskService.flush()
    if updateService is not None:
        updateService.apply()
    coroutineRunner.stop()
