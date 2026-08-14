from __future__ import annotations

import sys
from functools import cached_property
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QRect, QUrl, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QDesktopServices, QKeySequence, QPainter, QPalette, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    MSFluentWindow, FluentIcon, NavigationItemPosition, MessageBox, Theme, InfoBar, InfoBarPosition,
    SearchLineEdit, setThemeColor, IconWidget, SubtitleLabel, isDarkTheme,
)

from app.config.cfg import CloseMode, cfg
from app.config.constants import DONATE_URL, FEEDBACK_URL
from app.services.task_draft import TaskDraft
from app.signal_bus import signalBus
from app.services.update_service import UpdateState
from app.view.pages.setting_page import SettingPage
from app.view.pages.task_page import TaskPage

if TYPE_CHECKING:
    from qfluentwidgets import FluentIconBase
    from app.models.task import Task
    from app.services.browser_service import BrowserService
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.speed_meter import SpeedMeter
    from app.services.feature_service import FeatureService
    from app.services.task_service import TaskService
    from app.view.dialogs.task_draft import TaskDraftDialog


class DropOverlay(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._initWidget()
        self._initLayout()

    def _initWidget(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._icon = IconWidget(FluentIcon.FOLDER_ADD, self)
        self._icon.setFixedSize(48, 48)
        self._icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._label = SubtitleLabel(self.tr("松开以添加任务"), self)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.hide()

    def _initLayout(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(8)
        layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignCenter)

    def paintEvent(self, event):
        painter = QPainter(self)
        bgColor = QColor(0, 0, 0, 128) if isDarkTheme() else QColor(255, 255, 255, 180)
        painter.fillRect(self.rect(), bgColor)


class MainWindow(MSFluentWindow):

    def __init__(
        self,
        taskService: TaskService,
        featureService: FeatureService,
        browserService: BrowserService,
        categoryService: CategoryService,
        speedMeter: SpeedMeter,
        coroutineRunner: CoroutineRunner,
        plan,
        updateService=None,
        parent=None,
    ):
        self._isGeometryRestored = False
        self._isBackgroundEffectDirty = False
        self._macVisualEffectView = None
        self.searchEdit = None
        self._dropOverlay = None
        super().__init__(parent)
        self._taskService = taskService
        self._featureService = featureService
        self._browserService = browserService
        self._categoryService = categoryService
        self._coroutineRunner = coroutineRunner
        self._speedMeter = speedMeter
        self._updateService = updateService
        self._plan = plan
        self.setMicaEffectEnabled(False)
        if sys.platform != "darwin":
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._pages: dict[str, QWidget] = {}
        self._progressToast = None
        self._draft = TaskDraft(self._coroutineRunner, self._featureService, parent=self)
        self.searchEdit = SearchLineEdit(self.titleBar)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setWindowIcon(QIcon(":/image/logo.png"))
        self.setWindowTitle("Ghost Downloader")
        self.setMinimumSize(960, 540)
        if sys.platform == "win32":
            self._refreshBackgroundEffect()
        elif sys.platform == "darwin" and cfg.backgroundEffect.value != "None":
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.titleBar.hBoxLayout.insertSpacing(2, 6)
        if sys.platform == "darwin":
            self.titleBar.hBoxLayout.insertSpacing(0, 60)

        self.searchEdit.setClearButtonEnabled(True)
        self.searchEdit.hide()
        self.searchEdit.raise_()

        self.setAcceptDrops(True)
        self._dropOverlay = DropOverlay(self)

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
        for PageClass in self._featureService.pages():
            self._addPage(PageClass, PageClass.icon, PageClass.title,
                          NavigationItemPosition.TOP)

    def systemTitleBarRect(self, size) -> QRect:
        return QRect(0, 10, 75, size.height())

    def _normalBackgroundColor(self):
        if sys.platform == "darwin" and cfg.backgroundEffect.value != "None":
            if isDarkTheme():
                return QColor(0, 0, 0, 48)
            return QColor(255, 255, 255, 48)
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
            page = self._createPage(pageClass)
            page.setObjectName(routeKey)
            self.stackedWidget.addWidget(page)
            self._pages[routeKey] = page
            if self.stackedWidget.count() == 1:
                from qfluentwidgets.common import qrouter
                self.stackedWidget.currentChanged.connect(self._onCurrentInterfaceChanged)
                qrouter.setDefaultRouteKey(self.stackedWidget, routeKey)
        self.switchTo(page)
        self.navigationInterface.setCurrentItem(routeKey)
        self._updateSearchTarget(page)

    def _createPage(self, pageClass: type[QWidget]) -> QWidget:
        if pageClass is TaskPage:
            return TaskPage(
                self._taskService, self._featureService,
                self._categoryService, self._speedMeter, self._plan, parent=self,
            )
        if pageClass is SettingPage:
            return SettingPage(
                self._featureService, self._browserService,
                self._coroutineRunner, self._categoryService, self._taskService,
                self._updateService, parent=self,
            )
        return self._featureService.createPage(pageClass, parent=self)

    def _onSearchTextChanged(self, text: str) -> None:
        page = self.stackedWidget.currentWidget()
        if hasattr(page, 'setSearchText'):
            page.setSearchText(text)

    def _updateSearchTarget(self, page: QWidget) -> None:
        self.searchEdit.clear()
        if hasattr(page, 'searchPlaceholder'):
            self.searchEdit.setPlaceholderText(page.searchPlaceholder)
            self.searchEdit.show()
        else:
            self.searchEdit.hide()

    def _refreshSearchEditGeometry(self) -> None:
        tb = self.titleBar
        w = min(360, tb.width() - 300)
        w = max(200, w)
        self.searchEdit.setFixedWidth(w)
        x = (tb.width() - w) // 2
        y = (tb.height() - self.searchEdit.height()) // 2
        self.searchEdit.move(x, y)

    def _onSearchShortcut(self) -> None:
        if self.searchEdit.isVisible():
            self.searchEdit.setFocus()
            self.searchEdit.selectAll()

    def _bind(self) -> None:
        self._draft.taskConfirmed.connect(self._taskService.add)
        cfg.themeChanged.connect(self._setTheme)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._onSystemColorSchemeChanged)
        self.titleBar.closeBtn.clicked.disconnect(self.close)
        self.titleBar.closeBtn.clicked.connect(self._onCloseClicked)
        self.searchEdit.textChanged.connect(self._onSearchTextChanged)

        QShortcut(QKeySequence.StandardKey.Find, self).activated.connect(self._onSearchShortcut)

        if self._updateService is not None:
            self._updateService.changed.connect(self._onUpdateChanged)

        if sys.platform == "win32":
            cfg.backgroundEffect.valueChanged.connect(self._setBackgroundEffectWin)
        elif sys.platform == "darwin":
            cfg.backgroundEffect.valueChanged.connect(self._setBackgroundEffectMac)
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
        return TaskDraftDialog(
            self._draft, self._featureService, self._categoryService,
            parent=self,
        )

    def confirmPair(self, request) -> None:
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
            self._browserService.approvePair(session, requestId)
        else:
            self._browserService.rejectPair(session, requestId)

    def _onUpdateAvailable(self, info) -> None:
        from qfluentwidgets import PrimaryPushButton, PushButton

        if self._progressToast is not None:
            self._progressToast.deleteLater()
            self._progressToast = None

        infoBar = InfoBar(
            icon=FluentIcon.CLOUD,
            title=self.tr("检测到新版本"),
            content=self.tr("最新版本: {0}").format(info.latestVersion),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=-1,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self,
        )
        downloadButton = PrimaryPushButton(FluentIcon.DOWNLOAD, self.tr("立即下载"))
        if sys.platform == "linux":
            downloadButton.clicked.connect(lambda: (infoBar.close(), self._downloadBestAsset()))
        else:
            downloadButton.clicked.connect(lambda: (infoBar.close(), self._updateService.download("app")))
        infoBar.addWidget(downloadButton)
        detailButton = PushButton(FluentIcon.CHAT, self.tr("查看详情"))
        detailButton.clicked.connect(self._showReleaseDetails)
        infoBar.addWidget(detailButton)
        sponsorButton = PushButton(FluentIcon.HEART, self.tr("请作者喝咖啡"))
        sponsorButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DONATE_URL)))
        infoBar.addWidget(sponsorButton)
        infoBar.show()

    def _downloadBestAsset(self) -> None:
        from app.models.task import TaskOptions
        from app.update import fetchRelease, bestAsset

        def onFetched(release):
            asset = bestAsset(release)
            if asset is None:
                self._showReleaseDetails()
                return
            self._coroutineRunner.submit(
                self._featureService.parse(TaskOptions(url=asset.downloadUrl)),
                done=self._taskService.add,
                owner=self,
            )

        self._coroutineRunner.submit(fetchRelease(), done=onFetched, owner=self)

    def _onUpdateChanged(self, info) -> None:
        if info.targetId != "app":
            return
        if info.state not in (UpdateState.DOWNLOADING, UpdateState.READY, UpdateState.FAILED):
            return
        if self._progressToast is None:
            from app.view.components.progress_toast import ProgressToast
            self._progressToast = ProgressToast(
                onRetry=lambda: self._updateService.download("app"),
                parent=self,
            )
        self._progressToast.setInfo(info)

    def _showReleaseDetails(self) -> None:
        from app.models.task import TaskOptions
        from app.update import fetchRelease
        from app.view.dialogs.release_info import ReleaseInfoDialog

        def onFetched(release):
            dialog = ReleaseInfoDialog(release, self)
            dialog.accepted.connect(lambda: self._coroutineRunner.submit(
                self._featureService.parse(TaskOptions(url=dialog.selectedAsset().downloadUrl)),
                done=self._taskService.add,
                owner=self,
            ))
            dialog.open()

        self._coroutineRunner.submit(fetchRelease(), done=onFetched, owner=self)

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

        if sys.platform == "darwin" and mode != CloseMode.QUIT:
            if not self.isMaximized():
                cfg.set(cfg.geometry, self.geometry())
            self.hide()
            return

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

    def dragEnterEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase
        if any(d.isVisible() for d in self.findChildren(MaskDialogBase)):
            event.ignore()
            return
        event.acceptProposedAction()
        self._dropOverlay.setGeometry(self.rect())
        self._dropOverlay.show()
        self._dropOverlay.raise_()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._dropOverlay.hide()

    def dropEvent(self, event) -> None:
        self._dropOverlay.hide()
        urls = [u.toString() for u in event.mimeData().urls()]
        if urls:
            self.addUrls(urls)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._dropOverlay is not None and self._dropOverlay.isVisible():
            self._dropOverlay.setGeometry(self.rect())
        if self.searchEdit is not None and self.searchEdit.isVisible():
            self._refreshSearchEditGeometry()

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
        if self.searchEdit.isVisible():
            self._refreshSearchEditGeometry()
        if sys.platform == "darwin":
            self._refreshBackgroundEffect()

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
        if sys.platform in ("win32", "darwin"):
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
            self._setBackgroundEffectWin(cfg.backgroundEffect.value)
        elif sys.platform == "darwin":
            self._setBackgroundEffectMac(cfg.backgroundEffect.value)

    def _setBackgroundEffectWin(self, value: str) -> None:
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
            if isLessThanWin10():
                self.titleBar.closeBtn.hide()
                self.titleBar.minBtn.hide()
                self.titleBar.maxBtn.hide()
        elif value == "None":
            if isWin10():
                self.windowEffect.accentPolicy.AccentState = ACCENT_STATE.ACCENT_ENABLE_GRADIENT.value
                self.windowEffect.winCompAttrData.Attribute = WINDOWCOMPOSITIONATTRIB.WCA_ACCENT_POLICY.value
                self.windowEffect.SetWindowCompositionAttribute(int(self.winId()), pointer(self.windowEffect.winCompAttrData))
            self.setStyleSheet("")
            if isLessThanWin10():
                self.titleBar.closeBtn.show()
                self.titleBar.minBtn.show()
                self.titleBar.maxBtn.show()

    def paintEvent(self, e):
        if self._macVisualEffectView is not None:
            painter = QPainter(self)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), self.backgroundColor)
            # Source fill skips FluentWidget→MacFramelessWindow paint; re-apply traffic lights
            self._updateSystemTitleBar()
            return
        super().paintEvent(e)

    def _setBackgroundEffectMac(self, value: str) -> None:
        if value == "None":
            self._removeMacAcrylicEffect()
            return

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if not self.isVisible():
            self.backgroundColorAni.stop()
            self.setBackgroundColor(self._normalBackgroundColor())
            return

        if self._macVisualEffectView is not None:
            self._setMacAcrylicAppearance()
            self.backgroundColorAni.stop()
            self.setBackgroundColor(self._normalBackgroundColor())
            return

        import Cocoa
        from qframelesswindow.utils.mac_utils import getNSWindow

        nsWindow = getNSWindow(self.winId())
        contentView = nsWindow.contentView()
        superview = contentView.superview() if contentView is not None else None
        if contentView is None or superview is None:
            return

        visualEffectView = Cocoa.NSVisualEffectView.new()
        visualEffectView.setAutoresizingMask_(Cocoa.NSViewWidthSizable | Cocoa.NSViewHeightSizable)
        visualEffectView.setFrame_(contentView.frame())
        visualEffectView.setState_(Cocoa.NSVisualEffectStateActive)
        visualEffectView.setMaterial_(Cocoa.NSVisualEffectMaterialUnderWindowBackground)
        visualEffectView.setBlendingMode_(Cocoa.NSVisualEffectBlendingModeBehindWindow)
        superview.addSubview_positioned_relativeTo_(
            visualEffectView, Cocoa.NSWindowBelow, contentView)

        nsWindow.setOpaque_(False)
        nsWindow.setBackgroundColor_(Cocoa.NSColor.clearColor())
        self._macVisualEffectView = visualEffectView
        self._setMacAcrylicAppearance()
        self.backgroundColorAni.stop()
        self.setBackgroundColor(self._normalBackgroundColor())
        self._updateSystemTitleBar()

    def _removeMacAcrylicEffect(self) -> None:
        if self._macVisualEffectView is not None:
            import Cocoa
            from qframelesswindow.utils.mac_utils import getNSWindow

            self._macVisualEffectView.removeFromSuperview()
            self._macVisualEffectView = None
            nsWindow = getNSWindow(self.winId())
            nsWindow.setOpaque_(True)
            nsWindow.setBackgroundColor_(Cocoa.NSColor.windowBackgroundColor())

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.backgroundColorAni.stop()
        self.setBackgroundColor(self._normalBackgroundColor())
        if self.isVisible():
            self._updateSystemTitleBar()

    def _setMacAcrylicAppearance(self) -> None:
        import Cocoa
        name = Cocoa.NSAppearanceNameDarkAqua if isDarkTheme() else Cocoa.NSAppearanceNameAqua
        self._macVisualEffectView.setAppearance_(Cocoa.NSAppearance.appearanceNamed_(name))

if sys.platform == "darwin":
    import Cocoa
    from qframelesswindow.mac import MacFramelessWindowBase

    def _updateSystemTitleBar(self):
        self._extendTitleBarToClientArea()
        self.setSystemTitleBarButtonVisible(self.isSystemButtonVisible())
        nsWindow = self._MacFramelessWindowBase__nsWindow
        nsWindow.setMovableByWindowBackground_(False)
        nsWindow.setMovable_(False)
        nsWindow.setTitleVisibility_(Cocoa.NSWindowTitleHidden)

    MacFramelessWindowBase._updateSystemTitleBar = _updateSystemTitleBar


if sys.platform == "win32":
    from app.platform.windows import isLessThanWin10, isWin10

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
