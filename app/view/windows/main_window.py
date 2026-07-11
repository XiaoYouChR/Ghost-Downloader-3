from __future__ import annotations

import sys
from functools import cached_property
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QRect, QUrl, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QDesktopServices, QPalette
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget
from qfluentwidgets import (
    MSFluentWindow, FluentIcon, NavigationItemPosition, MessageBox, Theme, InfoBar, InfoBarPosition,
    setThemeColor,
)

from app.config.cfg import CloseMode, cfg
from app.config.constants import AUTHOR_URL, FEEDBACK_URL
from app.services.task_draft import TaskDraft
from app.services.task_service import taskService
from app.signal_bus import signalBus
from app.view.pages.setting_page import SettingPage
from app.view.pages.task_page import TaskPage

if TYPE_CHECKING:
    from qfluentwidgets import FluentIconBase
    from app.models.task import Task
    from app.view.dialogs.task_draft import TaskDraftDialog


class MainWindow(MSFluentWindow):

    def __init__(self, parent=None):
        self._isGeometryRestored = False
        self._isBackgroundEffectDirty = False
        super().__init__(parent)
        self.setMicaEffectEnabled(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._pages: dict[str, QWidget] = {}

        self._draft = TaskDraft(parent=self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setWindowIcon(QIcon(":/image/logo.png"))
        self.setWindowTitle("Ghost Downloader")
        self.setMinimumSize(960, 540)
        self._refreshBackgroundEffect()
        if sys.platform == "darwin":
            self.titleBar.hBoxLayout.insertSpacing(0, 60)

    def _initLayout(self) -> None:
        self._addPage(TaskPage, FluentIcon.DOWNLOAD, self.tr("下载任务"),
                      NavigationItemPosition.TOP)
        self.navigationInterface.addItem(
            routeKey="addTaskButton",
            text=self.tr("新建任务"),
            selectable=False,
            icon=FluentIcon.ADD,
            onClick=lambda: self.addUrls([]),
            position=NavigationItemPosition.TOP,
        )
        self._addPage(SettingPage, FluentIcon.SETTING, self.tr("设置"),
                      NavigationItemPosition.BOTTOM)
        self._showPage(TaskPage)

    def setupPacks(self) -> None:
        from app.services.feature_service import featureService
        for PageClass in featureService.pages():
            self._addPage(PageClass, PageClass.icon, PageClass.title,
                          NavigationItemPosition.TOP)

    def systemTitleBarRect(self, size) -> QRect:
        return QRect(0, 10, 75, size.height())

    def _normalBackgroundColor(self):
        from qfluentwidgets import isDarkTheme
        if self.styleSheet() == "":
            return self._darkBackgroundColor if isDarkTheme() else self._lightBackgroundColor
        return QColor(0, 0, 0, 0)

    def _addPage(self, pageClass: type[QWidget], icon: FluentIconBase, text: str,
                 position: NavigationItemPosition) -> None:
        self.navigationInterface.addItem(
            routeKey=pageClass.__name__, icon=icon, text=text,
            onClick=lambda: self._showPage(pageClass), position=position,
        )

    def _showPage(self, pageClass: type[QWidget]) -> None:
        routeKey = pageClass.__name__
        page = self._pages.get(routeKey)
        if page is None:
            page = pageClass(self)
            page.setObjectName(routeKey)
            self.stackedWidget.addWidget(page)
            self._pages[routeKey] = page
            if self.stackedWidget.count() == 1:
                from qfluentwidgets.common import qrouter
                self.stackedWidget.currentChanged.connect(self._onCurrentInterfaceChanged)
                qrouter.setDefaultRouteKey(self.stackedWidget, routeKey)
        self.switchTo(page)
        self.navigationInterface.setCurrentItem(routeKey)

    def _bind(self) -> None:
        self._draft.taskConfirmed.connect(taskService.add)
        cfg.themeChanged.connect(self._setTheme)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._onSystemColorSchemeChanged)
        self.titleBar.closeBtn.clicked.disconnect(self.close)
        self.titleBar.closeBtn.clicked.connect(self._onCloseClicked)

        if sys.platform == "win32":
            cfg.backgroundEffect.valueChanged.connect(self._setBackgroundEffect)
        if sys.platform == "darwin":
            from PySide6.QtGui import QKeySequence, QShortcut
            QShortcut(QKeySequence.StandardKey.Close, self).activated.connect(self._onCloseClicked)

    def addUrls(self, urls: list[str]) -> None:
        dialog = self._draftDialog
        if urls:
            dialog.addUrls(urls)
        if not dialog.isVisible():
            dialog.showMask()

    def addTasks(self, tasks: list[Task]) -> None:
        dialog = self._draftDialog
        dialog.addParsedTasks(tasks)
        if dialog.isActive:
            return
        if sys.platform == "darwin":
            self.show()
            from app.platform.desktop import raiseWindow
            raiseWindow(self)
            dialog.showMask()
        else:
            dialog.showStandalone()

    @cached_property
    def _draftDialog(self) -> TaskDraftDialog:
        from app.view.dialogs.task_draft import TaskDraftDialog
        return TaskDraftDialog(self._draft, parent=self)

    def confirmPair(self, request) -> None:
        from app.services.browser_service import browserService

        session = request["session"]
        requestId = request["requestId"]
        peerAddress = request.get("peerAddress", "")
        extensionVersion = request.get("extensionVersion", self.tr("未知"))
        clientKind = request.get("clientKind", self.tr("浏览器扩展"))

        content = self.tr(
            "浏览器扩展正在请求连接到 Ghost Downloader。\n\n"
            "来源: {0}\n客户端: {1}\n扩展版本: {2}\n\n"
            "仅在你刚刚点击扩展里的\"自动配对\"时允许。"
        ).format(peerAddress, clientKind, extensionVersion)

        dialog = MessageBox(self.tr("浏览器扩展配对请求"), content, self)
        dialog.yesButton.setText(self.tr("允许配对"))
        dialog.cancelButton.setText(self.tr("拒绝"))
        dialog.contentLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if dialog.exec():
            browserService.approvePair(session, requestId)
        else:
            browserService.rejectPair(session, requestId)

    def _onUpdateAvailable(self, release) -> None:
        from qfluentwidgets import PrimaryPushButton, PushButton
        from app.update import addBestAssetTask, showReleaseDialog

        infoBar = InfoBar(
            icon=FluentIcon.CLOUD,
            title=self.tr("检测到新版本"),
            content=self.tr("最新版本: {0}").format(release.version),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=-1,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self,
        )
        downloadButton = PrimaryPushButton(FluentIcon.DOWNLOAD, self.tr("立即下载"))
        downloadButton.clicked.connect(lambda: addBestAssetTask(release, self))
        infoBar.addWidget(downloadButton)
        detailButton = PushButton(FluentIcon.CHAT, self.tr("查看详情"))
        detailButton.clicked.connect(lambda: showReleaseDialog(release, self))
        infoBar.addWidget(detailButton)
        sponsorButton = PushButton(FluentIcon.HEART, self.tr("请作者喝咖啡"))
        sponsorButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(AUTHOR_URL)))
        infoBar.addWidget(sponsorButton)
        infoBar.show()

    def alertException(self, message: str) -> None:
        from qfluentwidgets import TransparentToolButton, ToolTipFilter

        dialog = MessageBox(
            self.tr("程序发生异常"),
            self.tr("点击\"确定\"后将复制错误信息并打开反馈页面。\n\n{0}").format(message),
            self,
        )
        logButton = TransparentToolButton(FluentIcon.DOCUMENT, dialog)
        logButton.setToolTip(self.tr("查看日志"))
        logButton.installEventFilter(ToolTipFilter(logButton))
        logButton.clicked.connect(self._openLogFolder)

        dialog.contentLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        titleLayout = dialog.textLayout
        titleLayout.removeWidget(dialog.titleLabel)
        titleRow = QHBoxLayout()
        titleRow.addWidget(dialog.titleLabel, 1)
        titleRow.addWidget(logButton)
        titleLayout.insertLayout(0, titleRow)

        if dialog.exec():
            QApplication.clipboard().setText(message)
            QDesktopServices.openUrl(QUrl(FEEDBACK_URL))

    def _openLogFolder(self) -> None:
        from app.config.paths import APP_DATA_DIR
        from app.platform.desktop import revealInFolder
        revealInFolder(f"{APP_DATA_DIR}/GhostDownloader.log")

    def _onCloseClicked(self) -> None:
        from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase
        for dialog in self.findChildren(MaskDialogBase):
            if dialog.isVisible():
                dialog.reject()
                return
        if sys.platform == "darwin" and self.isFullScreen():
            self.showNormal()
            QTimer.singleShot(1000, self._onCloseClicked)
            return

        mode = cfg.closeMode.value
        if mode == CloseMode.ASK:
            from qfluentwidgets import CheckBox
            dialog = MessageBox(
                self.tr("是否完全退出程序？"),
                self.tr("后台运行时可通过系统托盘图标重新打开。"),
                self,
            )
            dialog.yesButton.setText(self.tr("退出程序"))
            dialog.cancelButton.setText(self.tr("继续在后台运行"))
            checkbox = CheckBox(self.tr("记住我的选择"), dialog)
            dialog.textLayout.addWidget(checkbox)
            mode = CloseMode.QUIT if dialog.exec() else CloseMode.BACKGROUND
            if checkbox.isChecked():
                cfg.set(cfg.closeMode, mode)

        self.close()
        if mode == CloseMode.QUIT:
            QApplication.quit()

    def closeEvent(self, event) -> None:
        if event.spontaneous():
            event.ignore()
            self._onCloseClicked()
            return
        if not self.isMaximized():
            cfg.set(cfg.geometry, self.geometry())
        from app.view.qfw_patch import unregisterRouter
        unregisterRouter(self.stackedWidget)
        event.accept()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._isGeometryRestored:
            self._isGeometryRestored = True
            saved = cfg.geometry.value
            if saved.isValid() and QApplication.screenAt(saved.center()) is not None:
                self.setGeometry(saved)
            else:
                self.resize(960, 540)
                desktop = QApplication.primaryScreen().availableGeometry()
                self.move(desktop.center() - self.rect().center())

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self.refreshThemeColor()
        if self._isBackgroundEffectDirty and event.type() == QEvent.Type.ThemeChange:
            self._isBackgroundEffectDirty = False
            self._refreshBackgroundEffect()

    @staticmethod
    def refreshThemeColor() -> None:
        palette = QApplication.palette()
        for role in (QPalette.ColorRole.Accent, QPalette.ColorRole.Highlight):
            color = palette.color(role)
            if color.isValid() and cfg.themeColor.value != color:
                setThemeColor(color, save=False)
                return

    def _setTheme(self, value, deferBackgroundRefresh: bool = False) -> None:
        from qfluentwidgets import qconfig
        from qfluentwidgets.common.style_sheet import updateStyleSheet
        prevTheme = qconfig.theme
        qconfig.theme = value
        if qconfig.theme != prevTheme:
            qconfig.themeChanged.emit(qconfig.theme)
        updateStyleSheet()
        qconfig.themeChangedFinished.emit()
        from app.view.components.labels import IconBodyLabel
        IconBodyLabel.clearCache()
        if (
            deferBackgroundRefresh
            and sys.platform == "win32"
            and cfg.backgroundEffect.value in {"Mica", "MicaBlur", "MicaAlt"}
        ):
            self._isBackgroundEffectDirty = True
            return
        self._isBackgroundEffectDirty = False
        if sys.platform == "win32":
            self._refreshBackgroundEffect()

    def _onSystemColorSchemeChanged(self, colorScheme) -> None:
        if cfg.themeMode.value != Theme.AUTO:
            return
        if colorScheme == Qt.ColorScheme.Dark:
            self._setTheme(Theme.DARK, deferBackgroundRefresh=True)
        elif colorScheme == Qt.ColorScheme.Light:
            self._setTheme(Theme.LIGHT, deferBackgroundRefresh=True)
        else:
            self._setTheme(Theme.AUTO, deferBackgroundRefresh=True)

    def _refreshBackgroundEffect(self) -> None:
        if sys.platform == "win32":
            self._setBackgroundEffect(cfg.backgroundEffect.value)

    def _setBackgroundEffect(self, value) -> None:
        if sys.platform != "win32":
            return
        from qfluentwidgets import isDarkTheme
        self.windowEffect.removeBackgroundEffect(self.winId())
        isDark = isDarkTheme() if cfg.themeMode.value == Theme.AUTO else cfg.themeMode.value == Theme.DARK

        if value == "Acrylic":
            self.setStyleSheet("background-color: transparent")
            self.windowEffect.setAcrylicEffect(self.winId(), "00000030" if isDark else "FFFFFF30")
        elif value in {"Mica", "MicaBlur"}:
            self.setStyleSheet("background-color: transparent")
            self.windowEffect.setMicaEffect(self.winId(), isDark)
        elif value == "MicaAlt":
            self.setStyleSheet("background-color: transparent")
            self.windowEffect.setMicaEffect(self.winId(), isDark, isAlt=True)
        elif value == "Aero":
            self.setStyleSheet("background-color: transparent")
            self.windowEffect.setAeroEffect(self.winId())
            from app.platform.windows import isLessThanWin10
            if isLessThanWin10():
                self.titleBar.closeBtn.hide()
                self.titleBar.minBtn.hide()
                self.titleBar.maxBtn.hide()
        elif value == "None":
            self.setStyleSheet("")
            from app.platform.windows import isLessThanWin10
            if isLessThanWin10():
                self.titleBar.closeBtn.show()
                self.titleBar.minBtn.show()
                self.titleBar.maxBtn.show()


if sys.platform == "win32":
    from app.platform.windows import isWin10

    if isWin10():
        from ctypes import pointer
        from qframelesswindow import FramelessWindow, WindowEffect
        from qframelesswindow.windows.c_structures import ACCENT_STATE, WINDOWCOMPOSITIONATTRIB

        def _resetAcrylicEffect(self, hWnd):
            hWnd = int(hWnd)
            self.accentPolicy.AccentState = ACCENT_STATE.ACCENT_ENABLE_TRANSPARENTGRADIENT.value
            self.winCompAttrData.Attribute = WINDOWCOMPOSITIONATTRIB.WCA_ACCENT_POLICY.value
            self.SetWindowCompositionAttribute(hWnd, pointer(self.winCompAttrData))

        def _nativeEvent(self, eventType, message):
            if eventType == "windows_generic_MSG":
                from ctypes.wintypes import MSG
                msg = MSG.from_address(message.__int__())

                if cfg.backgroundEffect.value != "Acrylic":
                    return FramelessWindow.nativeEvent(self, eventType, message)

                WM_ENTERSIZEMOVE = 561
                WM_EXITSIZEMOVE = 562
                if msg.message == WM_ENTERSIZEMOVE:
                    self.windowEffect.resetAcrylicEffect(self.winId())
                elif msg.message == WM_EXITSIZEMOVE:
                    from qfluentwidgets import isDarkTheme
                    isDark = isDarkTheme() if cfg.themeMode.value == Theme.AUTO else cfg.themeMode.value == Theme.DARK
                    self.windowEffect.setAcrylicEffect(
                        self.winId(), "00000030" if isDark else "FFFFFF30",
                    )

            return FramelessWindow.nativeEvent(self, eventType, message)

        from qframelesswindow import AcrylicWindow

        WindowEffect.resetAcrylicEffect = _resetAcrylicEffect
        MainWindow.updateFrameless = AcrylicWindow.updateFrameless
        MainWindow.nativeEvent = _nativeEvent
