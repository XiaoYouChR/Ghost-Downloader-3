import sys
import traceback

from loguru import logger

from app.config.paths import APP_DATA_DIR

logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB", enqueue=False)


def _exceptionHook(exceptionType, value, tb):
    info = (exceptionType, value, tb)
    logger.opt(exception=info).error("Unhandled application exception")
    if "__compiled__" not in globals():
        sys.__excepthook__(*info)


sys.excepthook = _exceptionHook


def setupEnvironment():
    from app.config.cfg import cfg
    from app.config.constants import VERSION
    from app.platform.hidden_subprocess import setupHiddenSubprocess
    from qfluentwidgets import qconfig

    if sys.platform == "win32":
        setupHiddenSubprocess()

    import app.assets.resources  # noqa: F401
    from app.view.qfw_patch import patchFluentLabelThemeChanged
    from app.view.components.labels import IconBodyLabel
    patchFluentLabelThemeChanged()
    qconfig.themeChanged.connect(IconBodyLabel.clearCache)
    qconfig.load(f"{APP_DATA_DIR}/UserConfig.json", cfg)

    if sys.platform == "win32":
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
        font = QFont()
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        QApplication.setFont(font)

    logger.info("Ghost Downloader v{} launched", VERSION)


def startApp(application, isSilent=False):
    from PySide6.QtCore import QTranslator
    from PySide6.QtGui import QIcon
    from app.config.cfg import cfg
    from app.services.coroutine_runner import coroutineRunner
    from app.services.speed_meter import speedMeter
    from app.services.task_service import taskService
    from app.services.feature_service import featureService
    from app.services.browser_service import browserService
    from app.services.clipboard_listener import ClipboardListener
    from app.signal_bus import signalBus
    from app.view.windows.main_window import MainWindow

    def exceptionHook(exceptionType, value, tb):
        _exceptionHook(exceptionType, value, tb)
        message = "".join(traceback.format_exception(exceptionType, value, tb)).rstrip()
        signalBus.exceptionCaught.emit(message)

    sys.excepthook = exceptionHook

    application.setQuitOnLastWindowClosed(False)

    locale = cfg.language.value.value
    translator = QTranslator(application)
    translator.load(locale, "gd3", ".", ":/i18n")
    application.installTranslator(translator)

    if sys.platform == "darwin":
        from app.view.shell.dock import setDockIconVisible
        setDockIconVisible(cfg.shouldShowDockIcon.value, activate=False)
    coroutineRunner.start()

    from app.config.paths import clearUpdateDir
    clearUpdateDir()  # 启动清理：清空上次残留的更新文件（含崩溃留下的半成品）

    MainWindow.refreshThemeColor()
    window = MainWindow()

    if not isSilent:
        from qfluentwidgets import SplashScreen
        splash = SplashScreen(window.windowIcon(), window, enableShadow=False)
        splash.raise_()
        window.show()
        application.processEvents()

    featureService.load()
    from app.models.pack import PackConfig
    PackConfig.load()
    window.setupPacks()

    taskService.taskStarted.connect(lambda _: speedMeter.start())
    taskService.tasksAllCompleted.connect(speedMeter.stop)
    taskService.resumeSaved()
    featureService.start()

    if not isSilent:
        splash.finish()

    from app.platform.windows import emptyWorkingSet

    def emptyWorkingSetIfIdle():
        if window is None and taskService.runningCount() == 0:
            emptyWorkingSet()

    def onWindowDestroyed():
        nonlocal window
        window = None
        emptyWorkingSetIfIdle()

    window.destroyed.connect(onWindowDestroyed)

    def show() -> MainWindow:
        nonlocal window
        if window is None:
            window = MainWindow()
            window.setupPacks()
            window.destroyed.connect(onWindowDestroyed)
        window.show()
        from app.platform.desktop import raiseWindow
        raiseWindow(window)
        return window

    def onBrowserDraft(tasks):
        nonlocal window
        if window is None:
            window = MainWindow()
            window.setupPacks()
            window.destroyed.connect(onWindowDestroyed)
        window.addTasks(tasks)

    signalBus.activationRequested.connect(show)
    signalBus.openFileRequested.connect(lambda uris: show().addUrls(uris))
    signalBus.exceptionCaught.connect(lambda msg: show().alertException(msg))
    signalBus.updateAvailable.connect(lambda release: show()._onUpdateAvailable(release))
    browserService.taskDraftRequested.connect(onBrowserDraft)
    browserService.pairRequested.connect(lambda req: show().confirmPair(req))
    def onExtensionUpdated(version):
        from qfluentwidgets import InfoBar, InfoBarPosition
        w = show()
        InfoBar.success(w.tr("浏览器扩展已更新"), f"v{version}",
                        duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=w)

    browserService.extensionUpdated.connect(onExtensionUpdated)
    if cfg.isBrowserExtensionEnabled.value:
        browserService.start()
    cfg.isBrowserExtensionEnabled.valueChanged.connect(browserService.setEnabled)

    from app.services.aria2_rpc import aria2RpcServer
    aria2RpcServer.taskDraftRequested.connect(onBrowserDraft)
    if cfg.isAria2RpcEnabled.value:
        aria2RpcServer.start()
    cfg.isAria2RpcEnabled.valueChanged.connect(aria2RpcServer.setEnabled)
    cfg.aria2RpcPort.valueChanged.connect(aria2RpcServer.setPort)

    clipboardListener = ClipboardListener(parent=application)
    cfg.isClipboardListenerEnabled.valueChanged.connect(clipboardListener.setEnabled)
    clipboardListener.setEnabled(cfg.isClipboardListenerEnabled.value)
    clipboardListener.urlsDetected.connect(lambda urls: show().addUrls(urls))

    if sys.platform == "darwin":
        from app.view.shell.mac_status_item import MacStatusItem
        from app.view.shell.dock import setupDock
        statusItem = MacStatusItem()
        statusItem.show()
        speedMeter.speedChanged.connect(statusItem.setSpeed)
        application.statusItem = statusItem
        setupDock()
    else:
        from app.view.shell.tray import SystemTrayIcon
        tray = SystemTrayIcon(QIcon(":/image/logo.png"), parent=application)
        tray.show()

    from app.platform.android import IS_ANDROID
    if IS_ANDROID:
        from app.platform.android_notification import notifyTaskCompleted, notifyDiskSpaceInsufficient
    else:
        from app.platform.desktop_notification import init, notifyTaskCompleted, notifyDiskSpaceInsufficient
        coroutineRunner.submit(init())
    taskService.taskCompleted.connect(notifyTaskCompleted)
    taskService.diskSpaceInsufficient.connect(notifyDiskSpaceInsufficient)

    from app.services.plan import plan
    taskService.tasksAllCompleted.connect(plan.trigger)
    taskService.tasksAllCompleted.connect(emptyWorkingSetIfIdle)

    if isSilent:
        emptyWorkingSetIfIdle()

    if cfg.shouldCheckUpdateAtStartup.value:
        from app.update import fetchRelease, isOutdated

        def _onStartupReleaseFetched(release):
            if isOutdated(release):
                signalBus.updateAvailable.emit(release)

        coroutineRunner.submit(fetchRelease(), done=_onStartupReleaseFetched)

    def stopApp():
        taskService.stop()
        taskService.flush()
        browserService.stop()
        aria2RpcServer.stop()
        featureService.stop()
        coroutineRunner.stop()
        from app.config.paths import clearUpdateDir
        clearUpdateDir()  # 退出清理：不保留任何更新文件，压缩损坏半成品残留窗口

    application.aboutToQuit.connect(stopApp)


if __name__ == "__main__":
    from app.config.constants import DESKTOP_ID
    from app.platform.application import SingletonApplication

    setupEnvironment()
    app = SingletonApplication(sys.argv, DESKTOP_ID)
    startApp(app, isSilent="--silence" in sys.argv)
    sys.exit(app.exec())
