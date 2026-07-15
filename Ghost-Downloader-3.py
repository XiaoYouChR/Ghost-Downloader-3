import os
import sys
import traceback

from loguru import logger

from app.config.paths import APP_DATA_DIR

logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB")


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

        # https://github.com/python/cpython/issues/100256
        import mimetypes
        try:
            mimetypes.init()
        except OSError:
            mimetypes._mimetypes_read_windows_registry = None
            try:
                mimetypes.init()
            except OSError:
                pass
        if mimetypes._db is None:
            mimetypes._db = mimetypes.MimeTypes()

    import app.assets.resources  # noqa: F401
    from app.view.qfw_patch import patchFluentLabelThemeChanged, patchStackedWidgetAnimation
    from app.view.components.labels import IconBodyLabel
    patchFluentLabelThemeChanged()
    patchStackedWidgetAnimation()
    qconfig.themeChanged.connect(IconBodyLabel.clearCache)
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


def startApp(application, isSilent=False):
    from PySide6.QtGui import QIcon
    from app.config.cfg import cfg
    from app.services.browser_service import browserService
    from app.services.clipboard_listener import ClipboardListener
    from app.services.task_service import taskService
    from app.signal_bus import signalBus
    from app.startup import loadEngine, loadPacks, startEngine, bindNotifications, checkUpdateAtStartup, stopEngine
    from app.view.windows.main_window import MainWindow

    def exceptionHook(exceptionType, value, tb):
        _exceptionHook(exceptionType, value, tb)
        message = "".join(traceback.format_exception(exceptionType, value, tb)).rstrip()
        signalBus.exceptionCaught.emit(message)

    sys.excepthook = exceptionHook

    application.setQuitOnLastWindowClosed(False)

    if sys.platform == "darwin":
        from app.view.shell.dock import setDockIconVisible
        setDockIconVisible(cfg.shouldShowDockIcon.value, activate=False)

    loadEngine(application)

    MainWindow.refreshThemeColor()
    window = MainWindow()

    shouldRunOobe = not cfg.hasCompletedOobe.value and not isSilent

    if not isSilent and not shouldRunOobe:
        from qfluentwidgets import SplashScreen
        splash = SplashScreen(window.windowIcon(), window, enableShadow=False)
        splash.raise_()
        window.show()
        application.processEvents()

    loadPacks()
    window.setupPacks()
    startEngine()

    if not isSilent and not shouldRunOobe:
        splash.finish()

    if shouldRunOobe:
        # 首次启动：不显示主窗口，OOBE 完成后再进入
        from PySide6.QtCore import QEventLoop
        from app.view.windows.oobe_window import OobeWindow

        if cfg.isBrowserExtensionEnabled.value:
            browserService.start()  # 提前启动，OOBE 期间可完成扩展配对

        oobe = OobeWindow()
        browserService.pairRequested.connect(
            oobe.browserExtensionPage.onPairRequested
        )
        oobe.show()

        loop = QEventLoop()
        oobe.finished.connect(loop.quit)
        oobe.destroyed.connect(loop.quit)
        loop.exec()

        browserService.pairRequested.disconnect(
            oobe.browserExtensionPage.onPairRequested
        )
        # 必须在主线程显式销毁：闭包连接使窗口陷入循环引用，若留给
        # Python GC 会在任意工作线程 delete，主线程定时器表悬空 → 闪退
        oobe.deleteLater()
        window.show()

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
        from app.services.speed_meter import speedMeter
        statusItem = MacStatusItem()
        statusItem.show()
        speedMeter.speedChanged.connect(statusItem.setSpeed)
        application.statusItem = statusItem
        setupDock()
    else:
        from app.view.shell.tray import SystemTrayIcon
        tray = SystemTrayIcon(QIcon(":/image/logo.png"), parent=application)
        tray.show()

    from app.platform.desktop_notification import init, notifyTaskCompleted, notifyDiskSpaceInsufficient
    from app.services.coroutine_runner import coroutineRunner
    coroutineRunner.submit(init())
    bindNotifications(notifyTaskCompleted, notifyDiskSpaceInsufficient)

    from app.services.plan import plan
    taskService.tasksAllCompleted.connect(plan.trigger)
    taskService.tasksAllCompleted.connect(emptyWorkingSetIfIdle)

    if isSilent:
        emptyWorkingSetIfIdle()

    checkUpdateAtStartup()

    application.aboutToQuit.connect(stopEngine)


if __name__ == "__main__":
    from app.config.constants import DESKTOP_ID
    from app.platform.application import SingletonApplication

    setupEnvironment()
    app = SingletonApplication(sys.argv, DESKTOP_ID)
    startApp(app, isSilent="--silence" in sys.argv)
    sys.exit(app.exec())
