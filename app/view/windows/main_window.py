import sys
from pathlib import Path
from sys import platform
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import darkdetect
from PySide6.QtCore import QRect, QPropertyAnimation, Qt, QUrl, QEvent, QTimer
from PySide6.QtGui import QDesktopServices, QIcon, QColor, QPalette, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QDialog
from loguru import logger
from qfluentwidgets import MSFluentWindow, SplashScreen, FluentIcon, NavigationItemPosition, InfoBar, InfoBarPosition, \
    PushButton, PrimaryPushButton, setTheme, isDarkTheme, setThemeColor

from app.services.browser_service import BrowserService
from app.services.category_service import categoryService
from app.services.core_service import coreService
from app.services.feature_service import featureService
from app.supports.config import cfg, defaultHeaders, AUTHOR_URL, VERSION, FEEDBACK_URL, isWin10, \
    isLessThanWin10, toQFluentTheme
from app.services.task_service import taskService
from app.supports.signal_bus import signalBus
from app.supports.update import checkUpdate, UpdateState
from app.supports.file_open import fileUrisFromArgv
from app.supports.utils import getProxies, bringWindowToTop, showMessageBox, deduplicateFilename, openAppLogFolder
from app.view.components.add_task_dialog import AddTaskDialog
from app.view.components.labels import IconBodyLabel
from app.view.components.release_info_dialog import ReleaseInfoDialog
from app.view.components.tray import SystemTrayIcon
from app.view.pages.setting_page import SettingPage
from app.view.pages.task_page import TaskPage

if TYPE_CHECKING:
    from typing import Literal
    from PySide6.QtGui import QClipboard
    from PySide6.QtCore import QSize


class CustomSplashScreen(SplashScreen):

    def finish(self):
        """ fade out splash screen """
        opacityEffect = QGraphicsOpacityEffect(self)
        opacityEffect.setOpacity(1)
        self.setGraphicsEffect(opacityEffect)
        opacityAni = QPropertyAnimation(opacityEffect, b'opacity', self)
        opacityAni.setStartValue(1)
        opacityAni.setEndValue(0)
        opacityAni.setDuration(200)
        opacityAni.finished.connect(self.deleteLater)
        opacityAni.start()


class MainWindow(MSFluentWindow):
    def __init__(self, isSilently = False):
        self._pendingBackgroundEffectRefresh = False
        self._geometryApplied = False
        super().__init__(parent = None)
        self.setMicaEffectEnabled(False)    # 禁用 QFluentWidgets 管理的背景效果
        self.initWindow()
        if not isSilently:
            self.initSplashScreen()

        QApplication.processEvents()

        BrowserService.initialize(self)
        self.initPagesAndNavigation()

        self.clipboard: "QClipboard | None" = None
        # Fixes https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/442
        if QApplication.platformName() == "wayland":
            self._lastClipboardUrls: tuple[str, ...] = ()
        if sys.platform == "darwin":
            self._windowCloseShortcut = QShortcut(QKeySequence.StandardKey.Close, self)
            self._windowCloseShortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.tray = SystemTrayIcon(self)
        self.tray.show()

        self.connectSignalToSlot()
        # argv 里的文件延到事件循环: 此时 featurePacks 已加载, 也不会在构造期卡死在模态框
        QTimer.singleShot(0, lambda: signalBus.openFileRequested.emit(fileUrisFromArgv(sys.argv)))
        self._updateClipboardListener()
        self._toggleTheme(cfg.customThemeMode.value, triggeredByUser=True)
        self.updateThemeColor()

        if cfg.checkUpdateAtStartUp.value:
            self.checkForUpdates()

    def connectSignalToSlot(self):
        signalBus.showMainWindow.connect(lambda: bringWindowToTop(self))
        signalBus.catchException.connect(self._onExceptionCaught)
        signalBus.openFileRequested.connect(self.onOpenFileRequested)
        cfg.enableClipboardListener.valueChanged.connect(self._updateClipboardListener)
        cfg.customThemeMode.valueChanged.connect(
            lambda value: self._toggleTheme(value, triggeredByUser=True)
        )
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._onSystemColorSchemeChanged)
        if sys.platform == "darwin":
            self._windowCloseShortcut.activated.connect(self.close)
        if platform == 'win32':
            cfg.backgroundEffect.valueChanged.connect(self._setBackgroundEffect)

    def _onSystemColorSchemeChanged(self, colorScheme: Qt.ColorScheme):
        if cfg.customThemeMode.value != 'System':
            return

        if colorScheme == Qt.ColorScheme.Dark:
            self._toggleTheme('Dark')
        elif colorScheme == Qt.ColorScheme.Light:
            self._toggleTheme('Light')
        else:
            self._toggleTheme('System')

    def systemTitleBarRect(self, size: "QSize") -> "QRect":
        return QRect(0, 10, 75, size.height())

    def _normalBackgroundColor(self):
        if self.styleSheet() == "":
            return self._darkBackgroundColor if isDarkTheme() else self._lightBackgroundColor

        return QColor(0, 0, 0, 0)

    @staticmethod
    def updateThemeColor():
        palette = QApplication.palette()

        for role in (QPalette.ColorRole.Accent, QPalette.ColorRole.Highlight):
            color = palette.color(role)
            if not color.isValid() or cfg.themeColor.value == color:
                continue

            setThemeColor(color, save=False)
            return

    def _setBackgroundEffect(self, value: "Literal['Acrylic', 'Mica', 'MicaBlur', 'MicaAlt', 'Aero', 'None']"):
        if platform == 'win32':
            self.windowEffect.removeBackgroundEffect(self.winId())

            isDark = darkdetect.isDark() if cfg.customThemeMode.value == 'System' else cfg.customThemeMode.value == 'Dark'

            if value == 'Acrylic':
                self.setStyleSheet("background-color: transparent")
                self.windowEffect.setAcrylicEffect(self.winId(), "00000030" if isDark else "FFFFFF30")
            elif value == 'Mica':
                self.setStyleSheet("background-color: transparent")
                self.windowEffect.setMicaEffect(self.winId(), isDark)
            elif value == 'MicaBlur':
                self.windowEffect.setMicaEffect(self.winId(), isDark)
                self.setStyleSheet("background-color: transparent")
            elif value == 'MicaAlt':
                self.windowEffect.setMicaEffect(self.winId(), isDark, isAlt=True)
                self.setStyleSheet("background-color: transparent")
            elif value == 'Aero':
                self.windowEffect.setAeroEffect(self.winId())
                self.setStyleSheet("background-color: transparent")
                if isLessThanWin10():
                    self.titleBar.closeBtn.hide()
                    self.titleBar.minBtn.hide()
                    self.titleBar.maxBtn.hide()
            elif value == 'None':
                self.setStyleSheet("")
                if isLessThanWin10():
                    self.titleBar.closeBtn.show()
                    self.titleBar.minBtn.show()
                    self.titleBar.maxBtn.show()

    def _toggleTheme(
        self,
        value: "Literal['System', 'Dark', 'Light']",
        triggeredByUser: bool = False,
    ):
        setTheme(toQFluentTheme(value), save=False)

        IconBodyLabel.clearCache()

        if (
            not triggeredByUser
            and platform == 'win32'
            and cfg.backgroundEffect.value in ['Mica', 'MicaBlur', 'MicaAlt']
        ):
            self._pendingBackgroundEffectRefresh = True
            return

        self._pendingBackgroundEffectRefresh = False
        if platform == 'win32':
            self._setBackgroundEffect(cfg.backgroundEffect.value)

    def changeEvent(self, event):
        super().changeEvent(event)

        if event.type() == QEvent.Type.PaletteChange:
            self.updateThemeColor()

        if self._pendingBackgroundEffectRefresh and event.type() == QEvent.Type.ThemeChange:
            self._pendingBackgroundEffectRefresh = False
            self._setBackgroundEffect(cfg.backgroundEffect.value)

    def _updateClipboardListener(self):
        if self.clipboard is None:
            self.clipboard = QApplication.clipboard()
            if not cfg.enableClipboardListener.value:
                return

        if cfg.enableClipboardListener.value:
            self.clipboard.dataChanged.connect(self._onClipboardDataChanged)
        else:
            self.clipboard.dataChanged.disconnect(self._onClipboardDataChanged)

    def _onClipboardDataChanged(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard.ownsClipboard():
            return

        urls: list[str] = []
        for rawLine in clipboard.text().splitlines():
            url = rawLine.strip()
            if not url:
                continue
            try:
                parsed = urlparse(url)
            except ValueError as error:
                logger.warning("跳过无效剪贴板链接 {}: {}", url, error)
                continue
            if not parsed.scheme or not parsed.netloc or parsed.geturl() != url:
                continue
            if featureService.matches(url):
                urls.append(url)

        if not urls:
            return

        if QApplication.platformName() == "wayland":
            clipboardUrls = tuple(urls)
            if clipboardUrls == self._lastClipboardUrls:
                return
            self._lastClipboardUrls = clipboardUrls

        bringWindowToTop(self)
        self.showAddTaskDialog(urls=urls)

    def _onExceptionCaught(self, message: str):
        bringWindowToTop(self)
        showMessageBox(
            self,
            self.tr("程序发生异常"),
            self.tr("点击“确定”后将复制错误信息并打开反馈页面。\n点击“文档”图标以打开程序日志。\n{0}").format(message),
            showYesButton=True,
            yesSlot=lambda: (QApplication.clipboard().setText(message), QDesktopServices.openUrl(QUrl(FEEDBACK_URL))),
            actionIcon=FluentIcon.DOCUMENT,
            actionSlot=openAppLogFolder,
        )

    def showEvent(self, event):
        # pre-show 的 setGeometry 不会被 Qt 持久 commit，故首次可见时才恢复
        super().showEvent(event)
        if not self._geometryApplied:
            self._applyGeometry()
            self._geometryApplied = True

    def _applyGeometry(self):
        saved = cfg.geometry.value
        if saved.isValid() and QApplication.screenAt(saved.center()) is not None:
            self.setGeometry(saved)
        else:
            self._resetGeometry()

    def _resetGeometry(self):
        self.resize(960, 540)
        desktop = QApplication.primaryScreen().availableGeometry()
        self.move(desktop.center() - self.rect().center())

    def initWindow(self):
        self.setWindowIcon(QIcon(':/image/logo.png'))
        self.setWindowTitle('Ghost Downloader')
        self.setMinimumSize(960, 540)
        if sys.platform == 'darwin':
            self.titleBar.hBoxLayout.insertSpacing(0, 60)

    def initSplashScreen(self):
        self.splashScreen = CustomSplashScreen(self.windowIcon(), self, enableShadow=False)
        self.splashScreen.raise_()
        self.show()

    def initPagesAndNavigation(self):
        self.taskPage = TaskPage(self)
        self.settingPage = SettingPage(self)
        self.addSubInterface(self.taskPage, FluentIcon.DOWNLOAD, self.tr("下载任务"), position=NavigationItemPosition.TOP)
        self.navigationInterface.addItem(
            routeKey='addTaskButton',
            text=self.tr('新建任务'),
            selectable=False,
            icon=FluentIcon.ADD,
            onClick=self.showAddTaskDialog,
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(self.settingPage, FluentIcon.SETTING, self.tr("设置"), position=NavigationItemPosition.BOTTOM)

    def onOpenFileRequested(self, uris: list[str]):
        if not uris:
            return
        bringWindowToTop(self)
        self.showAddTaskDialog(urls=uris)

    def showAddTaskDialog(
            self,
            triggeredByUser: bool = False,
            urls: list[str] | None = None,
    ):
        dialog = AddTaskDialog.initialize(self)

        if urls:
            dialog.addUrls(urls)

        if dialog.isVisible() and not dialog.isStandaloneMode:
            dialog.raise_()
            dialog.activateWindow()
            return

        dialog.showMask()

    def showAddTaskDialogWithParsedTasks(self, tasks):
        dialog = AddTaskDialog.initialize(self)
        dialog.addParsedTasks(tasks)

        # macOS standalone 模式会强制唤起 MainWindow，只能用 mask
        if sys.platform == "darwin":
            bringWindowToTop(self)
            if not dialog.isVisible():
                dialog.showMask()
        else:
            dialog.showStandalone()

    def addTask(self, task) -> bool:
        try:
            if (
                cfg.enableCategory.value
                and task.category
                and task.path == Path(cfg.downloadFolder.value)
            ):
                folder = categoryService.folderOf(task.category)
                if folder:
                    task.applySettings({"path": Path(folder)})

            originalTitle = task.title
            if deduplicateFilename(task):
                logger.info("检测到重名文件，已自动重命名 {} -> {}", originalTitle, task.title)

            taskService.add(task)
            coreService.createTask(task)
            return True
        except Exception as e:
            logger.opt(exception=e).error("无法创建任务卡片 {}", task.title)
            return False

    def closeEvent(self, event):
        event.ignore()

        if sys.platform == 'darwin' and self.isFullScreen():
            self.showNormal()
            QTimer.singleShot(1000, self.hide)
            return

        if not self.isMaximized():
            cfg.set(cfg.geometry, self.geometry())

        self.hide()

    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            from ctypes.wintypes import MSG
            msg = MSG.from_address(message.__int__())

            if msg.message == 1024 + 1:  # WM_USER+1: 第二实例的唤醒请求
                bringWindowToTop(self)
                return True, 0
            # Win11 不打 isWin10 的 acrylic 补丁, WM_COPYDATA 只能在基类这条路接收
            if msg.message == 0x004A:
                from app.supports.file_open import fileUrisFromCopyData
                uris = fileUrisFromCopyData(msg.lParam)
                if uris:
                    signalBus.openFileRequested.emit(uris)
                    bringWindowToTop(self)
                    return True, 1

        return super().nativeEvent(eventType, message)

    def checkForUpdates(self, manual: bool = False):
        if manual:
            InfoBar.info(
                self.tr("检查更新"),
                self.tr("正在检查更新..."),
                duration=1500,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self,
            )
        coreService.runCoroutine(
            checkUpdate(),
            lambda state, error: self._onUpdateChecked(state, error, manual),
        )

    def _onUpdateChecked(self, state: UpdateState, error: str | None, manual: bool):
        if error:
            logger.warning("检查更新失败: {}", error)
            if manual:
                InfoBar.error(
                    self.tr("检查更新失败"),
                    self.tr("无法获取最新版本信息"),
                    duration=3000,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    parent=self,
                )
            return

        if not state.outdated:
            if manual:
                InfoBar.success(
                    self.tr("当前已是最新版本"),
                    self.tr("当前版本 {0}，最新版本 {1}").format(VERSION, state.latestVersion),
                    duration=3000,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    parent=self,
                )
            return

        if manual:
            self._showReleaseDialog(state.releaseData)
            return

        infoBar = InfoBar(
            icon=FluentIcon.CLOUD,
            title=self.tr('检测到新版本'),
            content=self.tr("最新版本: {0}").format(state.latestVersion),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=-1,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self,
        )
        infoBar.widgetLayout.addSpacing(10)
        downloadButton = PrimaryPushButton(FluentIcon.DOWNLOAD, self.tr('立即下载'))
        downloadButton.clicked.connect(lambda: self._downloadBestInstaller(state))
        infoBar.addWidget(downloadButton)
        detailButton = PushButton(FluentIcon.CHAT, self.tr('查看版本详细'))
        detailButton.clicked.connect(lambda: self._showReleaseDialog(state.releaseData))
        infoBar.addWidget(detailButton)
        sponsorButton = PushButton(FluentIcon.HEART, self.tr('请作者喝咖啡'))
        sponsorButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(AUTHOR_URL)))
        infoBar.addWidget(sponsorButton)
        infoBar.show()

    def _downloadBestInstaller(self, state: UpdateState):
        installer = state.installer
        if installer is None:
            InfoBar.warning(
                self.tr("未找到适配的安装包"),
                self.tr("已打开版本详情，请手动选择要下载的文件"),
                duration=3000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self,
            )
            self._showReleaseDialog(state.releaseData)
            return
        self._downloadInstaller(installer)

    def _downloadInstaller(self, installer: dict[str, Any]):
        installerName = installer["name"]
        payload = {
            "url": installer["browser_download_url"],
            "headers": defaultHeaders(),
            "proxies": getProxies(),
            "path": Path(cfg.downloadFolder.value),
        }
        coreService.runCoroutine(
            coreService._parse(payload),
            lambda task, error: self._onInstallerParsed(installerName, task, error),
        )

    def _onInstallerParsed(self, installerName: str, task, error: str | None):
        if error:
            logger.warning("创建更新下载任务失败 {}: {}", installerName, error)
            InfoBar.error(
                self.tr("创建下载任务失败"),
                installerName,
                duration=3000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self,
            )
            return

        if self.addTask(task):
            InfoBar.success(
                self.tr("已添加下载任务"),
                installerName,
                duration=2000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self,
            )

    def _showReleaseDialog(self, releaseData: dict):
        dialog = ReleaseInfoDialog(releaseData, self, False)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._downloadInstaller(dialog.selectedAsset())
        dialog.deleteLater()

if isWin10():
    from qframelesswindow import AcrylicWindow, FramelessWindow, WindowEffect
    from qframelesswindow.windows.c_structures import ACCENT_STATE, WINDOWCOMPOSITIONATTRIB
    from ctypes import pointer

    def resetAcrylicEffect(self, hWnd):
        hWnd = int(hWnd)

        self.accentPolicy.AccentState = ACCENT_STATE.ACCENT_ENABLE_TRANSPARENTGRADIENT.value
        self.winCompAttrData.Attribute = WINDOWCOMPOSITIONATTRIB.WCA_ACCENT_POLICY.value
        self.SetWindowCompositionAttribute(hWnd, pointer(self.winCompAttrData))

    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            from ctypes.wintypes import MSG
            msg = MSG.from_address(message.__int__())

            # WIN_USER = 1024
            if msg.message == 561 and cfg.backgroundEffect.value == "Acrylic":
                self.windowEffect.resetAcrylicEffect(self.winId())
            elif msg.message == 562 and cfg.backgroundEffect.value == "Acrylic":
                isDark = darkdetect.isDark() if cfg.customThemeMode.value == 'System' else cfg.customThemeMode.value == 'Dark'
                self.windowEffect.setAcrylicEffect(self.winId(), "00000030" if isDark else "FFFFFF30")
            elif msg.message == 1024 + 1:
                bringWindowToTop(self)
                return True, 0
            elif msg.message == 0x004A:  # WM_COPYDATA: 第二实例转发来的待打开 URI
                from app.supports.file_open import fileUrisFromCopyData
                uris = fileUrisFromCopyData(msg.lParam)
                if uris:
                    signalBus.openFileRequested.emit(uris)
                    bringWindowToTop(self)
                    return True, 1

        return FramelessWindow.nativeEvent(self, eventType, message)

    WindowEffect.resetAcrylicEffect = resetAcrylicEffect
    MainWindow.updateFrameless = AcrylicWindow.updateFrameless
    MainWindow.nativeEvent = nativeEvent
