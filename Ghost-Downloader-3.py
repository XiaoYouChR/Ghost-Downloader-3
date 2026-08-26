import os
import sys
import traceback

from loguru import logger

from app.config.paths import APP_DATA_DIR

logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB", retention=5)


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
    import shutil
    from PySide6.QtGui import QIcon
    from app.config.cfg import cfg
    from app.config.paths import executableDir
    from app.services.clipboard_listener import ClipboardListener
    from app.signal_bus import signalBus
    from app.startup import loadEngine, createServices, loadPacks, startEngine, bindNotifications, checkUpdateAtStartup, stopEngine
    from app.view.windows.main_window import MainWindow

    def exceptionHook(exceptionType, value, tb):
        _exceptionHook(exceptionType, value, tb)
        message = "".join(traceback.format_exception(exceptionType, value, tb)).rstrip()
        signalBus.exceptionCaught.emit(message)

    sys.excepthook = exceptionHook

    families = [application.font().defaultFamily()]
    if sys.platform == "darwin":
        families.append("PingFang SC")
    elif sys.platform == "win32":
        families.append("Microsoft YaHei UI")
    cfg.set(cfg.fontFamilies, families, save=False)
    application.setQuitOnLastWindowClosed(False)

    if sys.platform == "darwin":
        from app.view.shell.dock import setDockIconVisible
        setDockIconVisible(cfg.shouldShowDockIcon.value, activate=False)

    coroutineRunner, categoryService, speedMeter = loadEngine(application)

    appDir = executableDir.parent.parent if sys.platform == "darwin" else executableDir
    backupDir = appDir.parent / f"{appDir.name}_backup"
    if backupDir.is_dir():
        shutil.rmtree(backupDir, ignore_errors=True)

    MainWindow.refreshThemeColor()

    featureService, taskService, browserService, aria2RpcServer, updateService, runtimeStatusService = createServices(
        coroutineRunner, categoryService, speedMeter,
    )
    loadPacks(featureService, coroutineRunner, speedMeter)

    from app.services.plan import Plan
    plan = Plan(allCompleted=lambda: taskService.runningCount() == 0)
    taskService.tasksAllCompleted.connect(plan.trigger)

    application.clipboardListener = ClipboardListener(featureService.matchPassive, parent=application)
    cfg.isClipboardListenerEnabled.valueChanged.connect(application.clipboardListener.setEnabled)
    application.clipboardListener.setEnabled(cfg.isClipboardListenerEnabled.value)

    shouldRunOobe = not cfg.hasCompletedOobe.value and not isSilent

    if shouldRunOobe:
        # 首次启动：服务先就绪，主窗口等 OOBE 结束后按最终配置创建
        from PySide6.QtCore import QEventLoop
        from app.view.windows.oobe_window import OobeWindow

        startEngine(taskService, speedMeter, featureService, coroutineRunner)

        if cfg.isBrowserExtensionEnabled.value:
            browserService.start()  # 提前启动，OOBE 期间可完成扩展配对

        oobe = OobeWindow(browserService, coroutineRunner, featureService, runtimeStatusService)
        browserService.pairRequested.connect(oobe.onPairRequested)
        oobe.show()

        loop = QEventLoop()
        oobe.finished.connect(loop.quit)
        oobe.destroyed.connect(loop.quit)
        loop.exec()

        browserService.pairRequested.disconnect(oobe.onPairRequested)
        # 必须在主线程显式销毁：闭包连接使窗口陷入循环引用，若留给
        # Python GC 会在任意工作线程 delete，主线程定时器表悬空 → 闪退
        oobe.deleteLater()

        window = MainWindow(taskService, featureService, browserService, categoryService, speedMeter, coroutineRunner, plan, updateService)
        window.setupPacks()
        window.show()
    else:
        window = MainWindow(taskService, featureService, browserService, categoryService, speedMeter, coroutineRunner, plan, updateService)

        if not isSilent and sys.platform != "darwin":
            from qfluentwidgets import SplashScreen
            splash = SplashScreen(window.windowIcon(), window, enableShadow=False)
            splash.raise_()
            window.show()
            application.processEvents()

        window.setupPacks()
        startEngine(taskService, speedMeter, featureService, coroutineRunner)

        if not isSilent and sys.platform != "darwin":
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
            window = MainWindow(taskService, featureService, browserService, categoryService, speedMeter, coroutineRunner, plan, updateService)
            window.setupPacks()
            window.destroyed.connect(onWindowDestroyed)
        window.show()
        from app.platform.desktop import raiseWindow
        raiseWindow(window)
        return window

    def onBrowserDraft(tasks):
        nonlocal window
        if window is None:
            window = MainWindow(taskService, featureService, browserService, categoryService, speedMeter, coroutineRunner, plan, updateService)
            window.setupPacks()
            window.destroyed.connect(onWindowDestroyed)
        window.addTasks(tasks)

    if sys.platform != "darwin":
        signalBus.activationRequested.connect(show)
    signalBus.openUriRequested.connect(lambda uris: show().addUrls(uris))
    signalBus.exceptionCaught.connect(lambda msg: show().alertException(msg))
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

    aria2RpcServer.taskDraftRequested.connect(onBrowserDraft)
    if cfg.isAria2RpcEnabled.value:
        aria2RpcServer.start()
    cfg.isAria2RpcEnabled.valueChanged.connect(aria2RpcServer.setEnabled)
    cfg.aria2RpcPort.valueChanged.connect(aria2RpcServer.setPort)

    application.clipboardListener.urlsDetected.connect(lambda urls: show().addUrls(urls))

    if sys.platform == "darwin":
        from app.view.shell.mac_status_item import MacStatusItem
        from app.view.shell.dock import setupDock
        statusItem = MacStatusItem(taskService)
        statusItem.show()
        speedMeter.speedChanged.connect(statusItem.setSpeed)
        application.statusItem = statusItem
        setupDock(speedMeter, taskService)
    else:
        from app.view.shell.tray import SystemTrayIcon
        tray = SystemTrayIcon(taskService, speedMeter, QIcon(":/image/logo.png"), parent=application)
        tray.show()

    from app.platform.desktop_keepalive import hold, release
    taskService.taskStarted.connect(hold)
    taskService.tasksAllCompleted.connect(release)

    from app.platform.desktop_notification import init, notifyTaskCompleted, notifyDiskSpaceInsufficient
    coroutineRunner.submit(init(coroutineRunner.submit))
    bindNotifications(taskService, notifyTaskCompleted, notifyDiskSpaceInsufficient)

    taskService.tasksAllCompleted.connect(emptyWorkingSetIfIdle)

    if isSilent:
        emptyWorkingSetIfIdle()

    if sys.platform == "darwin":
        signalBus.activationRequested.connect(show)

    from app.services.update_service import UpdateState
    def onUpdateChanged(info):
        if info.targetId == "app" and info.state == UpdateState.AVAILABLE:
            show()._onUpdateAvailable(info)
        elif info.targetId != "app" and info.state == UpdateState.AVAILABLE:
            updateService.download(info.targetId)
        elif info.targetId != "app" and info.state == UpdateState.READY:
            if window is not None:
                from qfluentwidgets import InfoBar, InfoBarPosition
                InfoBar.success(
                    window.tr("功能包更新"),
                    window.tr("{0} 将在下次启动时生效").format(info.label),
                    duration=5000,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    parent=window,
                )
    updateService.changed.connect(onUpdateChanged)
    checkUpdateAtStartup(updateService)

    application.aboutToQuit.connect(lambda: stopEngine(taskService, browserService, aria2RpcServer, featureService, coroutineRunner, updateService))


if __name__ == "__main__":
    from app.config.constants import DESKTOP_ID
    from app.platform.application import SingletonApplication
    from app.platform.url_scheme import isWakeUri

    setupEnvironment()
    app = SingletonApplication(sys.argv, DESKTOP_ID)
    isSilent = "--silence" in sys.argv or any(isWakeUri(arg) for arg in sys.argv[1:])
    startApp(app, isSilent=isSilent)
    sys.exit(app.exec())
