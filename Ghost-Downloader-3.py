from __future__ import annotations

import gc
import os
import sys
import traceback
from contextlib import suppress
from typing import TYPE_CHECKING

from app.config.paths import APP_DATA_DIR

if TYPE_CHECKING:
    from app.platform.application import Application
    from app.platform.instance import PrimaryInstance


def _exceptionHook(exceptionType, value, tb):
    from loguru import logger
    info = (exceptionType, value, tb)
    logger.opt(exception=info).error("Unhandled application exception")
    if "__compiled__" not in globals():
        sys.__excepthook__(*info)


def setupEnvironment() -> None:
    from loguru import logger
    logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB", retention=5)
    sys.excepthook = _exceptionHook

    from app.config.cfg import cfg
    from app.config.constants import VERSION
    from app.platform.hidden_subprocess import setupHiddenSubprocess
    from qfluentwidgets import qconfig

    if sys.platform == "win32":
        setupHiddenSubprocess()

    from app.view.qfw_patch import (
        patchLinuxFrameless, patchMacFrameless, patchMaskDialogAnimation, patchWindowsFrameless,
    )
    # Wayland 上在绘制中截图会递归重绘，卡住合成器 #1017
    if sys.platform != "linux":
        patchMaskDialogAnimation()
    else:
        patchLinuxFrameless()
    if sys.platform == "win32":
        patchWindowsFrameless()
    elif sys.platform == "darwin":
        patchMacFrameless()
    qconfig.load(f"{APP_DATA_DIR}/UserConfig.json", cfg)

    if cfg.dpiScale.value != 0:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.dpiScale.value)

    if sys.platform == "win32":
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
        font = QFont()
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        QApplication.setFont(font)

    logger.info("Ghost Downloader v{} launched", VERSION)


def startApp(application: Application, primaryInstance: PrimaryInstance, isSilent: bool = False) -> None:
    from PySide6.QtGui import QIcon
    from app.config.cfg import cfg
    from app.view.dialogs.name_conflict import NameConflictPrompt
    from app.view.shell.clipboard_listener import ClipboardListener
    from app.signal_bus import signalBus
    from app.services.port_listener import ListenStatus
    from app.services.update_service import UpdateService
    from app.startup import loadResources, setupThemeColor, createEngine, deleteBackupDir, loadPacks, checkUpdateAtStartup

    def exceptionHook(exceptionType, value, tb):
        _exceptionHook(exceptionType, value, tb)
        message = "".join(traceback.format_exception(exceptionType, value, tb)).rstrip()
        signalBus.exceptionCaught.emit(message)

    sys.excepthook = exceptionHook

    from PySide6.QtCore import QLocale
    from app.platform.desktop import buildFontFamilies
    localeName = cfg.language.value
    locale = QLocale() if localeName == "Auto" else QLocale(localeName)
    cfg.set(cfg.fontFamilies, buildFontFamilies(locale, application.font().defaultFamily()), save=False)
    application.setQuitOnLastWindowClosed(False)

    if sys.platform == "win32":
        from app.platform.windows import setAnimationFrameRate
        setAnimationFrameRate(application.primaryScreen().refreshRate())

    if sys.platform == "darwin":
        from app.view.shell.dock import setDockIconVisible
        setDockIconVisible(cfg.shouldShowDockIcon.value, activate=False)

    loadResources(application)
    engine = createEngine(application)
    coroutineRunner, taskService, featureService = engine.coroutineRunner, engine.taskService, engine.featureService
    browserService, speedMeter = engine.browserService, engine.speedMeter

    setupThemeColor(application)

    updateService = UpdateService(coroutineRunner)

    from app.services.plan import Plan
    plan = Plan(allCompleted=lambda: taskService.runningCount() == 0)
    taskService.tasksAllCompleted.connect(plan.trigger)

    from app.platform.desktop_keepalive import buildSleepInhibitor
    taskService.runningChanged.connect(buildSleepInhibitor())

    application.clipboardListener = ClipboardListener(featureService.matchPassive, parent=application)
    cfg.isClipboardListenerEnabled.valueChanged.connect(application.clipboardListener.setEnabled)
    application.clipboardListener.setEnabled(cfg.isClipboardListenerEnabled.value)

    application.nameConflictPrompt = NameConflictPrompt(engine.nameConflictQueue)

    from app.platform.windows import emptyWorkingSet

    window: MainWindow | None = None

    def emptyWorkingSetIfIdle():
        if window is None and taskService.runningCount() == 0:
            emptyWorkingSet()

    def onWindowDestroyed():
        nonlocal window
        window = None
        from PySide6.QtGui import QPixmapCache
        from app.view.components.labels import IconBodyLabel
        QPixmapCache.clear()
        IconBodyLabel.clearCache()
        gc.collect()
        emptyWorkingSetIfIdle()

    def createWindow() -> MainWindow:
        nonlocal window
        from app.view.windows.main_window import MainWindow
        window = MainWindow(taskService, featureService, browserService, engine.browserListener, engine.aria2RpcListener, engine.categoryService, speedMeter, coroutineRunner, plan, updateService)
        window.destroyed.connect(onWindowDestroyed)
        return window

    def show() -> MainWindow:
        if window is None:
            createWindow().setupPacks()
        window.show()
        from app.platform.desktop import raiseWindow
        raiseWindow(window)
        return window

    def onTaskDraftRequested(tasks, error):
        if window is None:
            createWindow().setupPacks()
        window.addTasks(tasks, error)

    def onExtensionUpdated(version):
        from qfluentwidgets import InfoBar, InfoBarPosition
        w = show()
        InfoBar.success(w.tr("浏览器扩展已更新"), f"v{version}",
                        duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=w)

    browserService.taskDraftRequested.connect(onTaskDraftRequested)
    browserService.extensionUpdated.connect(onExtensionUpdated)
    engine.aria2RpcService.taskDraftRequested.connect(onTaskDraftRequested)

    shouldRunOobe = not cfg.hasCompletedOobe.value and not isSilent

    if shouldRunOobe:
        # 首次启动：服务先就绪，主窗口等 OOBE 结束后按最终配置创建
        from PySide6.QtCore import QEventLoop
        from app.view.windows.oobe_window import OobeWindow

        loadPacks(featureService, coroutineRunner, speedMeter)
        engine.start()
        deleteBackupDir()

        oobe = OobeWindow(browserService, engine.browserListener, coroutineRunner, featureService, engine.runtimeStatusService)
        def onOobePairRequestChanged(request):
            if request is not None:
                oobe.onPairRequested(request)

        browserService.pairRequestChanged.connect(onOobePairRequestChanged)
        oobe.show()

        loop = QEventLoop()
        oobe.finished.connect(loop.quit)
        oobe.destroyed.connect(loop.quit)
        loop.exec()

        browserService.pairRequestChanged.disconnect(onOobePairRequestChanged)
        # 必须在主线程显式销毁：闭包连接使窗口陷入循环引用，若留给
        # Python GC 会在任意工作线程 delete，主线程定时器表悬空 → 闪退
        oobe.deleteLater()

        show()
    elif isSilent:
        loadPacks(featureService, coroutineRunner, speedMeter)
        engine.start()
        deleteBackupDir()
    elif sys.platform == "darwin":
        loadPacks(featureService, coroutineRunner, speedMeter)
        show()
        engine.start()
        deleteBackupDir()
    else:
        from qfluentwidgets import SplashScreen
        createWindow()
        splash = SplashScreen(window.windowIcon(), window, enableShadow=False)
        splash.raise_()
        window.show()
        application.processEvents()

        loadPacks(featureService, coroutineRunner, speedMeter)
        window.setupPacks()
        engine.start()
        deleteBackupDir()

        splash.finish()

    from qfluentwidgets import qconfig
    from app.view.components.labels import IconBodyLabel
    qconfig.themeChanged.connect(IconBodyLabel.clearCache)

    if sys.platform != "darwin":
        signalBus.activationRequested.connect(show)
    signalBus.exceptionCaught.connect(lambda msg: show().onExceptionCaught(msg))
    engine.browserListener.stateChanged.connect(
        lambda state: state.status == ListenStatus.FAILED and show().onBrowserListenFailed(state.error))
    engine.aria2RpcListener.stateChanged.connect(
        lambda state: state.status == ListenStatus.FAILED and show().onAria2ListenFailed(state.error))

    if sys.platform == "darwin":
        from app.view.shell.mac_status_item import MacStatusItem
        from app.view.shell.dock import setupDock
        statusItem = MacStatusItem(taskService, show)
        statusItem.show()
        speedMeter.speedChanged.connect(statusItem.setSpeed)
        application.statusItem = statusItem
        setupDock(speedMeter, taskService)
    else:
        from app.view.shell.tray import SystemTrayIcon
        tray = SystemTrayIcon(taskService, speedMeter, show, QIcon(":/image/logo.png"), parent=application)
        tray.show()
    if sys.platform == "linux":
        from app.platform.taskbar import setLauncherProgress
        speedMeter.speedChanged.connect(lambda _: setLauncherProgress(taskService.overallProgress()))

    from app.platform.desktop_notification import (
        buildClipboardRequest, buildPairRequest, buildParseFailed,
    )
    from app.view.shell.notifier import Notifier

    activate = signalBus.activationRequested.emit
    notifier = Notifier(
        taskService, speedMeter.speedChanged, coroutineRunner.submit, activate,
        isWindowAway=lambda: window is None or not window.isVisible() or window.isMinimized(),
    )
    signalBus.taskPopupRequested.connect(notifier.openTaskPopup)
    engine.aria2RpcService.parseFailed.connect(
        lambda url, error: notifier.send(buildParseFailed(url, error, activate)))
    application.clipboardListener.urlsDetected.connect(lambda urls: notifier.request(
        "clipboard",
        buildClipboardRequest(urls, lambda: show().addUrls(urls)) if cfg.isClipboardRequestEnabled.value else None,
        lambda: show().addUrls(urls),
    ))
    browserService.pairRequestChanged.connect(lambda req: notifier.request(
        "pair",
        buildPairRequest(req, lambda: browserService.approvePair(req.requestId),
                         lambda: browserService.rejectPair(req.requestId)) if req else None,
        (lambda: show().onPairRequested(req)) if req else None,
    ))

    taskService.tasksAllCompleted.connect(emptyWorkingSetIfIdle)

    if isSilent:
        emptyWorkingSetIfIdle()

    if sys.platform == "darwin":
        signalBus.activationRequested.connect(show)

    from app.services.update_service import UpdateState
    def onUpdateChanged(info):
        if info.targetId == "app" and info.state == UpdateState.AVAILABLE:
            show().onUpdateAvailable(info)
        elif info.targetId != "app" and info.state == UpdateState.AVAILABLE:
            updateService.download(info.targetId)
        elif info.targetId != "app" and info.state == UpdateState.READY:
            if window is not None:
                window.showPackUpdateReady(info.label)
    updateService.changed.connect(onUpdateChanged)
    checkUpdateAtStartup(updateService)

    def onTerminated() -> None:
        with suppress(RuntimeError):
            application.aboutToQuit.disconnect(updateService.apply)

    application.aboutToQuit.connect(notifier.close)
    application.aboutToQuit.connect(engine.stop)
    application.aboutToQuit.connect(updateService.apply)
    application.aboutToQuit.connect(coroutineRunner.stop)
    application.terminated.connect(onTerminated)
    if sys.platform == "win32":
        from app.platform.windows import ShutdownListener
        shutdownListener = ShutdownListener(
            application.translate("Shutdown", "正在保存任务进度"),
            icon=QIcon(":/image/logo.png"),
        )
        application.shutdownListener = shutdownListener
        shutdownListener.triggered.connect(onTerminated)
        application.aboutToQuit.connect(shutdownListener.close)

    from app.cli import Cli
    cli = Cli(taskService, featureService.parse, coroutineRunner.submit,
              open=lambda uris: show().addUrls(uris), activate=show)
    primaryInstance.start(cli.run)


if __name__ == "__main__":
    from app.platform import instance

    # 打包版的 argv[0] 被 Nuitka 换成真实路径，只有 original_argv0 还保留 ghd
    argv = [__compiled__.original_argv0, *sys.argv[1:]] if "__compiled__" in globals() else sys.argv
    if (exitCode := instance.request(argv, os.getcwd())) is not None:
        sys.exit(exitCode)

    from app.cli import isSilent
    from app.platform.application import Application

    setupEnvironment()
    app = Application(sys.argv)
    primaryInstance = instance.open(app, argv, os.getcwd())
    if primaryInstance is None:
        sys.exit(0)
    startApp(app, primaryInstance, isSilent=isSilent(argv[1:]))
    exitCode = app.exec()
    primaryInstance.close()
    sys.exit(exitCode)
