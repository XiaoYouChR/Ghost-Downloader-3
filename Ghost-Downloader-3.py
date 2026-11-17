from __future__ import annotations

import os
import sys
import traceback
from dataclasses import replace
from typing import TYPE_CHECKING

from app.config.paths import APP_DATA_DIR

if TYPE_CHECKING:
    from types import TracebackType
    from desktop_notifier.common import Notification
    from app.models.task import Task, TaskError, TaskOptions
    from app.platform.application import Application
    from app.platform.instance import PrimaryInstance
    from app.services.browser_service import PairRequest
    from app.services.update_service import UpdateInfo


def _exceptionHook(exceptionType: type[BaseException], value: BaseException, tb: TracebackType | None) -> None:
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
        patchLinuxFrameless, patchMaskDialogAnimation, patchStackedWidgetAnimation, patchWindowsFrameless,
    )
    from app.view.components.labels import IconBodyLabel
    patchStackedWidgetAnimation()
    # Wayland 上在绘制中截图会递归重绘，卡住合成器 #1017
    if sys.platform != "linux":
        patchMaskDialogAnimation()
    else:
        patchLinuxFrameless()
    if sys.platform == "win32":
        patchWindowsFrameless()
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


def startApp(application: Application, primaryInstance: PrimaryInstance, isSilent: bool = False) -> None:
    from PySide6.QtGui import QIcon
    from app.config.cfg import NoticeStyle, TaskPopupPlace, cfg
    from app.view.dialogs.name_conflict import NameConflictPrompt
    from app.view.shell.clipboard_listener import ClipboardListener
    from app.signal_bus import signalBus
    from app.services.port_listener import ListenStatus
    from app.services.update_service import UpdateService
    from app.startup import loadResources, setupThemeColor, createEngine, deleteBackupDir, deleteLegacyAppIdFiles, loadPacks, checkUpdateAtStartup
    from app.view.windows.main_window import MainWindow

    def exceptionHook(exceptionType: type[BaseException], value: BaseException, tb: TracebackType | None) -> None:
        _exceptionHook(exceptionType, value, tb)
        message = "".join(traceback.format_exception(exceptionType, value, tb)).rstrip()
        signalBus.exceptionCaught.emit(message)

    sys.excepthook = exceptionHook

    from PySide6.QtCore import QLocale
    from app.platform.desktop import buildFontFamilies
    localeName = cfg.language.value.value
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

    deleteBackupDir()
    if deleteLegacyAppIdFiles():
        from app.platform.file_association import registerUrlScheme
        from app.platform.run_at_login import setRunAtLogin
        if cfg.isUrlSchemeRegistered.value:
            registerUrlScheme()
        if cfg.shouldRunAtLogin.value:
            setRunAtLogin(True)

    setupThemeColor(application)

    updateService = UpdateService(coroutineRunner)
    loadPacks(featureService, coroutineRunner, speedMeter)

    from app.services.plan import Plan
    plan = Plan(allCompleted=lambda: taskService.runningCount() == 0)
    taskService.tasksAllCompleted.connect(plan.trigger)

    application.clipboardListener = ClipboardListener(featureService.matchPassive, parent=application)
    cfg.isClipboardListenerEnabled.valueChanged.connect(application.clipboardListener.setEnabled)
    application.clipboardListener.setEnabled(cfg.isClipboardListenerEnabled.value)

    application.nameConflictPrompt = NameConflictPrompt(engine.nameConflictQueue)

    from app.platform.windows import emptyWorkingSet

    window: MainWindow | None = None

    def emptyWorkingSetIfIdle() -> None:
        if window is None and taskService.runningCount() == 0:
            emptyWorkingSet()

    def onWindowDestroyed() -> None:
        nonlocal window
        window = None
        emptyWorkingSetIfIdle()

    def createWindow() -> MainWindow:
        nonlocal window
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

    def onTaskDraftRequested(tasks: list[TaskOptions], error: TaskError | None) -> None:
        if window is None:
            createWindow().setupPacks()
        window.addTasks(tasks, error)

    def onExtensionUpdated(version: str) -> None:
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

        engine.start()

        oobe = OobeWindow(browserService, engine.browserListener, coroutineRunner, featureService, engine.runtimeStatusService)
        def onOobePairRequestChanged(request: PairRequest | None) -> None:
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
    else:
        createWindow()

        if not isSilent and sys.platform != "darwin":
            from qfluentwidgets import SplashScreen
            splash = SplashScreen(window.windowIcon(), window, enableShadow=False)
            splash.raise_()
            window.show()
            application.processEvents()

        window.setupPacks()
        engine.start()

        if not isSilent and sys.platform != "darwin":
            splash.finish()

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

    from app.platform.desktop_keepalive import hold, release
    taskService.taskStarted.connect(lambda _: hold())
    taskService.tasksAllCompleted.connect(release)

    from app.platform.desktop_notification import (
        PopupNotifier, PopupStack, SystemNotifier, buildClipboardRequest,
        buildDiskSpaceInsufficient, buildPairRequest, buildParseFailed, buildTaskCompleted, buildTaskFailed,
        createDoNotDisturb, toFileIcon,
    )
    systemNotifier = SystemNotifier(coroutineRunner.submit)
    sendTo = {NoticeStyle.SYSTEM: systemNotifier.send, NoticeStyle.OFF: lambda _: None}
    popupStack: PopupStack | None = None
    popupNotifier: PopupNotifier | None = None
    if NoticeStyle.POPUP in cfg.noticeStyle.options:
        doNotDisturb = createDoNotDisturb()
        popupStack = PopupStack(doNotDisturb)
        popupNotifier = PopupNotifier(popupStack)
        sendTo[NoticeStyle.POPUP] = popupNotifier.send
        # 先于 onAboutToQuit 连接，engine.stop() 期间再来的 Notice 会被忽略
        application.aboutToQuit.connect(doNotDisturb.close)
        application.aboutToQuit.connect(popupStack.clear)

    def windowIsAway() -> bool:
        return window is None or not window.isVisible() or window.isMinimized()

    def onUrlsDetected(urls: list[str]) -> None:
        if not cfg.isClipboardRequestEnabled.value or not windowIsAway() or popupNotifier is None:
            show().addUrls(urls)
            return
        popupNotifier.send(buildClipboardRequest(urls, lambda: show().addUrls(urls)), "clipboard")

    def onPairRequestChanged(request: PairRequest | None) -> None:
        if request is None or not windowIsAway() or popupNotifier is None:
            if popupStack is not None:
                popupStack.close("pair")
            if request is not None:
                show().onPairRequested(request)
            return
        popupNotifier.send(buildPairRequest(
            request, lambda: browserService.approvePair(request.requestId),
            lambda: browserService.rejectPair(request.requestId)), "pair")

    application.clipboardListener.urlsDetected.connect(onUrlsDetected)
    browserService.pairRequestChanged.connect(onPairRequestChanged)
    activate = signalBus.activationRequested.emit

    def sendNotice(notification: Notification) -> None:
        if not cfg.isNoticeSoundEnabled.value:
            notification = replace(notification, sound=None)
        sendTo[cfg.noticeStyle.value](notification)

    candidates: set[str] = set()

    def showTaskPopup(task: Task, minimized: bool) -> None:
        if popupStack is None:
            return
        popupId = f"task:{task.taskId}"
        if (popup := popupStack.popup(popupId)) is not None:
            if minimized or not popup.isMinimized():
                return
            if popupStack.countShown("task:") >= 3:
                return
            popup.showNormal()
            return
        if not minimized and popupStack.countShown("task:") >= 3:
            return
        from app.view.shell.task_popup import TaskPopup
        popup = TaskPopup(task, taskService, speedMeter.speedChanged)
        popup.openOnTaskbar = minimized
        popupStack.add(popup)

    def onTaskAdded(task: Task) -> None:
        candidates.add(task.taskId)

    def onTaskStarted(task: Task) -> None:
        if task.taskId not in candidates:
            return
        candidates.discard(task.taskId)
        if (popupStack is None or cfg.noticeStyle.value != NoticeStyle.POPUP
                or cfg.taskPopupPlace.value == TaskPopupPlace.OFF):
            return
        showTaskPopup(task, minimized=cfg.taskPopupPlace.value == TaskPopupPlace.TASKBAR)

    def onTaskRemoved(taskId: str) -> None:
        candidates.discard(taskId)
        if popupStack is not None:
            popupStack.close(f"task:{taskId}")

    def onTaskCompleted(task: Task) -> None:
        notice = buildTaskCompleted(task, toFileIcon(task.outputPath))
        popupId = f"task:{task.taskId}"
        if popupNotifier is not None and popupStack is not None and popupStack.has(popupId):
            if not cfg.isNoticeSoundEnabled.value:
                notice = replace(notice, sound=None)
            popupNotifier.send(notice, popupId)
            return
        sendNotice(notice)

    def onTaskFailed(task: Task) -> None:
        popupId = f"task:{task.taskId}"
        if popupNotifier is not None and popupStack is not None and popupStack.has(popupId):
            popupNotifier.send(buildTaskFailed(task, activate), popupId)

    if popupStack is not None:
        taskService.taskAdded.connect(onTaskAdded)
        taskService.taskStarted.connect(onTaskStarted)
        taskService.taskRemoved.connect(onTaskRemoved)
        taskService.taskFailed.connect(onTaskFailed)
        signalBus.taskPopupRequested.connect(lambda task: showTaskPopup(task, minimized=False))
    taskService.taskCompleted.connect(onTaskCompleted)
    taskService.diskSpaceInsufficient.connect(
        lambda free, needed: sendNotice(buildDiskSpaceInsufficient(free, needed, activate)))
    engine.aria2RpcService.parseFailed.connect(lambda url, error: sendNotice(buildParseFailed(url, error, activate)))

    taskService.tasksAllCompleted.connect(emptyWorkingSetIfIdle)

    if isSilent:
        emptyWorkingSetIfIdle()

    if sys.platform == "darwin":
        signalBus.activationRequested.connect(show)

    from app.services.update_service import UpdateState
    def onUpdateChanged(info: UpdateInfo) -> None:
        if info.targetId == "app" and info.state == UpdateState.AVAILABLE:
            show().onUpdateAvailable(info)
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

    def onAboutToQuit() -> None:
        engine.stop()
        updateService.apply()
        coroutineRunner.stop()

    application.aboutToQuit.connect(onAboutToQuit)

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
