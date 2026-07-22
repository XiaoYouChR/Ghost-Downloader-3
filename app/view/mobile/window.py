from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import QApplication, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon, InfoBar, InfoBarPosition, PrimaryToolButton, SearchLineEdit,
    Theme, isDarkTheme, qconfig,
)

from app.config.cfg import cfg
from app.platform.android import clearShare, isStorageGranted, requestStoragePermission, sharedText, toTaskUrls
from app.platform.android_notification import isNotificationEnabled, requestNotificationPermission
from app.services.task_draft import TaskDraft
from app.view.dialogs.task_draft import TaskDraftDialog
from app.view.mobile.device import setupAccentColor
from app.view.mobile.navigation import BottomNavigationBar
from app.view.mobile.permission import PermissionBanner
from app.view.mobile.setting_page import MobileSettingPage
from app.view.mobile.task_page import MobileTaskPage

if TYPE_CHECKING:
    from app.services.browser_service import BrowserService
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.feature_service import FeatureService
    from app.services.speed_meter import SpeedMeter
    from app.services.task_service import TaskService

TASK_PAGE_INDEX = 0


class MobileMainWindow(QWidget):
    def __init__(
        self,
        taskService: TaskService,
        featureService: FeatureService,
        browserService: BrowserService,
        categoryService: CategoryService,
        speedMeter: SpeedMeter,
        coroutineRunner: CoroutineRunner,
    ):
        super().__init__(parent=None)
        self._taskService = taskService
        self._featureService = featureService
        self._browserService = browserService
        self._categoryService = categoryService
        self._speedMeter = speedMeter
        self._coroutineRunner = coroutineRunner
        setupAccentColor()

        self.stackedWidget = QStackedWidget(self)
        self.navigationBar = BottomNavigationBar(self)
        self.permissionBanner = PermissionBanner(requestStoragePermission, parent=self)
        self.notificationBanner = PermissionBanner(
            requestNotificationPermission,
            text=self.tr("未开启通知权限，下载完成后将无法提醒"),
            parent=self,
        )
        self.taskPage = MobileTaskPage(taskService, featureService, categoryService, speedMeter, coroutineRunner, parent=self)
        self.settingPage = MobileSettingPage(featureService, browserService, coroutineRunner, categoryService, parent=self)
        self.searchEdit = SearchLineEdit(self)
        self.addButton = PrimaryToolButton(FluentIcon.ADD, self)
        self.vBoxLayout = QVBoxLayout(self)

        self._draft = TaskDraft(coroutineRunner, featureService, parent=self)
        self._draftDialog = TaskDraftDialog(self._draft, featureService, categoryService, parent=self)
        self._shareDraft = TaskDraft(coroutineRunner, featureService, parent=self)

        self._initWidget()
        self._initLayout()
        self._bind()
        self._updatePermissionBanner()
        self._updateAddButtonVisibility()
        self._updateSearchTarget(self.taskPage)

    def _initWidget(self):
        self.setObjectName("MobileMainWindow")
        self.setWindowIcon(QIcon(":/image/logo.png"))
        self.setWindowTitle("Ghost Downloader")
        self.taskPage.setObjectName("taskInterface")
        self.settingPage.setObjectName("settingInterface")
        self.searchEdit.setClearButtonEnabled(True)
        self.addButton.setFixedSize(56, 56)
        self.addButton.setIconSize(QSize(22, 22))
        self.addButton.raise_()
        self._addPage(self.taskPage, FluentIcon.DOWNLOAD, self.tr("任务"))
        self._addPage(self.settingPage, FluentIcon.SETTING, self.tr("设置"))

    def _initLayout(self):
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.permissionBanner, 0)
        self.vBoxLayout.addWidget(self.notificationBanner, 0)
        searchBar = QWidget(self)
        searchBarLayout = QHBoxLayout(searchBar)
        searchBarLayout.setContentsMargins(10, 4, 10, 2)
        searchBarLayout.addWidget(self.searchEdit)
        self.vBoxLayout.addWidget(searchBar, 0)
        self.vBoxLayout.addWidget(self.stackedWidget, 1)
        self.vBoxLayout.addWidget(self.navigationBar, 0)

    def _bind(self):
        self.navigationBar.currentChanged.connect(self.stackedWidget.setCurrentIndex)
        self.navigationBar.currentChanged.connect(lambda *_: self._updateAddButtonVisibility())
        self.navigationBar.currentChanged.connect(
            lambda index: self._updateSearchTarget(self.stackedWidget.widget(index))
        )
        self.searchEdit.textChanged.connect(self._onSearchTextChanged)
        self.taskPage.selectionModeChanged.connect(lambda *_: self._updateAddButtonVisibility())
        self.addButton.clicked.connect(self._showAddTaskDialog)
        self._draft.taskConfirmed.connect(self._taskService.add)
        self._shareDraft.taskConfirmed.connect(self._taskService.add)
        QApplication.instance().applicationStateChanged.connect(self._onApplicationStateChanged)
        cfg.themeChanged.connect(self._setTheme)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._onSystemColorSchemeChanged)
        qconfig.themeChanged.connect(self.update)

    def _addPage(self, page: QWidget, icon: FluentIcon, text: str):
        self.stackedWidget.addWidget(page)
        self.navigationBar.addItem(icon, text)

    def _onSearchTextChanged(self, text: str) -> None:
        page = self.stackedWidget.currentWidget()
        if hasattr(page, 'setSearchText'):
            page.setSearchText(text)

    def _updateSearchTarget(self, page: QWidget) -> None:
        self.searchEdit.clear()
        if hasattr(page, 'setSearchText'):
            self.searchEdit.setPlaceholderText(page.searchPlaceholder)
            self.searchEdit.show()
        else:
            self.searchEdit.hide()

    def _onSystemColorSchemeChanged(self, colorScheme):
        if cfg.themeMode.value != Theme.AUTO:
            return
        if colorScheme == Qt.ColorScheme.Dark:
            self._setTheme(Theme.DARK)
        elif colorScheme == Qt.ColorScheme.Light:
            self._setTheme(Theme.LIGHT)
        else:
            self._setTheme(Theme.AUTO)

    def _setTheme(self, value):
        from qfluentwidgets.common.style_sheet import updateStyleSheet
        prevTheme = qconfig.theme
        qconfig.theme = value
        if qconfig.theme != prevTheme:
            qconfig.themeChanged.emit(qconfig.theme)
        updateStyleSheet()
        qconfig.themeChangedFinished.emit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            setupAccentColor()

    def _onApplicationStateChanged(self, state: Qt.ApplicationState):
        if state == Qt.ApplicationState.ApplicationActive:
            self._updatePermissionBanner()
            self._addSharedTasks()

    def _addSharedTasks(self) -> None:
        text = sharedText()
        if text is None:
            return
        clearShare()
        urls = toTaskUrls(text)
        if not urls:
            return
        if cfg.shouldDraftTakenDownload.value or not isStorageGranted():
            self._draftDialog.addUrls(urls)
            self._draftDialog.showMask()
            return
        self.navigationBar.setCurrentIndex(TASK_PAGE_INDEX)
        self._shareDraft.setUrls(urls)
        self._shareDraft.confirm()

    def _updatePermissionBanner(self):
        self.permissionBanner.setVisible(not isStorageGranted())
        self.notificationBanner.setVisible(not isNotificationEnabled())

    def _updateAddButtonVisibility(self):
        onTaskPage = self.stackedWidget.currentIndex() == TASK_PAGE_INDEX
        self.addButton.setVisible(onTaskPage and not self.taskPage.isSelectionMode)

    def _showAddTaskDialog(self):
        if not isStorageGranted():
            requestStoragePermission()
            InfoBar.warning(
                self.tr("需要存储权限"),
                self.tr("请授予存储权限后再新建任务"),
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        self._draftDialog.widget.setFixedWidth(min(700, self.width() - 24))
        if self._draftDialog.isVisible():
            self._draftDialog.raise_()
            self._draftDialog.activateWindow()
            return
        self._draftDialog.showMask()

    def _onUpdateAvailable(self, release) -> None:
        from qfluentwidgets import PrimaryPushButton, PushButton
        from app.update import addBestAssetTask, showReleaseDialog

        infoBar = InfoBar(
            icon=FluentIcon.CLOUD,
            title=self.tr("检测到新版本"),
            content=self.tr("最新版本: {0}").format(release.version),
            orient=Qt.Orientation.Vertical,
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
        infoBar.show()

    def alertException(self, message: str) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QHBoxLayout
        from qfluentwidgets import MessageBox, ToolTipFilter, TransparentToolButton

        from app.config.constants import FEEDBACK_URL
        from app.config.paths import APP_DATA_DIR
        from app.platform.android import openFile

        dialog = MessageBox(
            self.tr("程序发生异常"),
            self.tr('点击"确定"后将复制错误信息并打开反馈页面。\n\n{0}').format(message),
            self,
        )
        logButton = TransparentToolButton(FluentIcon.DOCUMENT, dialog)
        logButton.setToolTip(self.tr("查看日志"))
        logButton.installEventFilter(ToolTipFilter(logButton))
        logButton.clicked.connect(lambda: openFile(f"{APP_DATA_DIR}/GhostDownloader.log"))

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 16
        self.addButton.move(
            self.width() - self.addButton.width() - margin,
            self.height() - self.navigationBar.height() - self.addButton.height() - margin,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(32, 32, 32) if isDarkTheme() else QColor(243, 243, 243))
