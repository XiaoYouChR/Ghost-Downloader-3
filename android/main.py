import os
import sys
import traceback
from pathlib import Path

from loguru import logger

from app.config.paths import APP_DATA_DIR

Path(APP_DATA_DIR).mkdir(parents=True, exist_ok=True)
logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB")


def _exceptionHook(exceptionType, value, tb):
    info = (exceptionType, value, tb)
    logger.opt(exception=info).error("Unhandled application exception")


sys.excepthook = _exceptionHook


def setupEnvironment():
    import warnings
    from qfluentwidgets import qconfig
    from app.config.cfg import cfg
    from app.config.constants import VERSION
    from app.platform.android import nativeLibraryDir

    from app.view.qfw_patch import patchFluentLabelThemeChanged, patchStackedWidgetAnimation
    from app.view.components.labels import IconBodyLabel
    patchFluentLabelThemeChanged()
    patchStackedWidgetAnimation()
    qconfig.themeChanged.connect(IconBodyLabel.clearCache)
    qconfig.load(f"{APP_DATA_DIR}/UserConfig.json", cfg)
    logger.info("Ghost Downloader v{} (Android) launched", VERSION)

    if cfg.dpiScale.value != 0:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.dpiScale.value)

    warnings.warn = logger.warning
    nativeLibraryDir()


def startApp(application):
    from app.config.cfg import cfg
    from app.platform.android_keepalive import keepAlive, REASON_DOWNLOAD, REASON_BROWSER, requestIgnoreBatteryOptimizations
    from app.platform.android_notification import (
        notifyBrowserPaired, notifyBrowserTaskAdded, notifyDiskSpaceInsufficient,
        notifyTaskCompleted,
    )
    from app.signal_bus import signalBus
    from app.startup import loadEngine, loadPacks, createEngine, startEngine, bindNotifications, checkUpdateAtStartup, stopEngine
    from app.view.mobile.device import setupTouchScrolling
    from app.view.mobile.window import MobileMainWindow

    def exceptionHook(exceptionType, value, tb):
        _exceptionHook(exceptionType, value, tb)
        message = "".join(traceback.format_exception(exceptionType, value, tb)).rstrip()
        signalBus.exceptionCaught.emit(message)

    sys.excepthook = exceptionHook

    coroutineRunner, categoryService, speedMeter = loadEngine(application)
    featureService = loadPacks()
    taskService, browserService, aria2RpcServer, runtimeStatusService = createEngine(coroutineRunner, categoryService, speedMeter, featureService)

    mainWindow = MobileMainWindow(taskService, featureService, browserService, categoryService, speedMeter, coroutineRunner)
    mainWindow.show()
    setupTouchScrolling(mainWindow)

    taskService.taskStarted.connect(lambda _: keepAlive.holdFor(REASON_DOWNLOAD))
    taskService.tasksAllCompleted.connect(lambda: keepAlive.release(REASON_DOWNLOAD))
    speedMeter.speedChanged.connect(keepAlive.setSpeed)

    startEngine(taskService, speedMeter, featureService, coroutineRunner, categoryService, runtimeStatusService)

    signalBus.exceptionCaught.connect(mainWindow.alertException)

    requestIgnoreBatteryOptimizations()

    bindNotifications(taskService, notifyTaskCompleted, notifyDiskSpaceInsufficient)

    def onBrowserTaskDraftRequested(tasks):
        for task in tasks:
            taskService.add(task)
        notifyBrowserTaskAdded(tasks)

    def onBrowserPairRequested(request):
        browserService.approvePair(request["session"], request["requestId"])
        notifyBrowserPaired(request.get("peerAddress", ""))

    browserService.taskDraftRequested.connect(onBrowserTaskDraftRequested)
    browserService.pairRequested.connect(onBrowserPairRequested)

    aria2RpcServer.taskDraftRequested.connect(onBrowserTaskDraftRequested)
    if cfg.isAria2RpcEnabled.value:
        aria2RpcServer.start()
    cfg.isAria2RpcEnabled.valueChanged.connect(aria2RpcServer.setEnabled)
    cfg.aria2RpcPort.valueChanged.connect(aria2RpcServer.setPort)

    def onBrowserExtensionToggled(enabled):
        if enabled:
            keepAlive.holdFor(REASON_BROWSER)
        else:
            keepAlive.release(REASON_BROWSER)
        browserService.setEnabled(enabled)

    cfg.isBrowserExtensionEnabled.valueChanged.connect(onBrowserExtensionToggled)
    if cfg.isBrowserExtensionEnabled.value:
        keepAlive.holdFor(REASON_BROWSER)
        browserService.start()

    checkUpdateAtStartup(coroutineRunner, onUpdateAvailable=mainWindow._onUpdateAvailable)

    application.aboutToQuit.connect(lambda: stopEngine(taskService, browserService, aria2RpcServer, featureService, coroutineRunner))


if __name__ == "__main__":
    from app.platform.application import SingletonApplication

    setupEnvironment()
    app = SingletonApplication(sys.argv, "gd3")
    # setupAndroid 须在 QApplication 之后: setupFont 的 QFontDatabase 需要 QGuiApplication
    from app.view.mobile import setupAndroid
    setupAndroid()
    startApp(app)
    sys.exit(app.exec())
