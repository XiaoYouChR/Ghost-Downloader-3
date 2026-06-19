from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette
from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget
from loguru import logger
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PrimaryToolButton,
    Theme,
    isDarkTheme,
    qconfig,
    setTheme,
    setThemeColor,
)

from app.services.browser_service import BrowserService
from app.services.core_service import coreService
from app.services.task_service import taskService
from app.supports.android import isStorageGranted, requestStoragePermission
from app.supports.config import cfg, toQFluentTheme
from app.view.components.labels import IconBodyLabel
from app.view.mobile.navigation import BottomNavigationBar
from app.view.mobile.permission import PermissionBanner
from app.view.mobile.setting_page import MobileSettingPage
from app.view.mobile.task_page import MobileTaskPage

class MobileMainWindow(QWidget):
    def __init__(self):
        super().__init__(parent=None)
        self.updateThemeColor()
        BrowserService.initialize(self)
        self.stackedWidget = QStackedWidget(self)
        self.navigationBar = BottomNavigationBar(self)
        self.vBoxLayout = QVBoxLayout(self)
        self.permissionBanner = PermissionBanner(requestStoragePermission, self)
        self.taskPage = MobileTaskPage(self, onSelectionModeChanged=self._updateAddButtonVisibility)
        self.settingPage = MobileSettingPage(self)
        self.addButton = PrimaryToolButton(FluentIcon.ADD, self)
        self._initWidget()
        self._initLayout()
        self._bind()
        self._updatePermissionBanner()

    def _initWidget(self):
        self.setObjectName("MobileMainWindow")
        self.setWindowIcon(QIcon(":/image/logo.png"))
        self.setWindowTitle("Ghost Downloader")
        self.taskPage.setObjectName("taskInterface")
        self.settingPage.setObjectName("settingInterface")
        self.addButton.setFixedSize(56, 56)
        self.addButton.setIconSize(QSize(22, 22))
        self.addButton.raise_()
        self.addPage(self.taskPage, FluentIcon.DOWNLOAD, self.tr("任务"))
        self.addPage(self.settingPage, FluentIcon.SETTING, self.tr("设置"))

    def _initLayout(self):
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.permissionBanner, 0)
        self.vBoxLayout.addWidget(self.stackedWidget, 1)
        self.vBoxLayout.addWidget(self.navigationBar, 0)

    def _bind(self):
        self.navigationBar.currentChanged.connect(self.stackedWidget.setCurrentIndex)
        self.navigationBar.currentChanged.connect(lambda *_: self._updateAddButtonVisibility())
        self.addButton.clicked.connect(self.showAddTaskDialog)
        QApplication.instance().applicationStateChanged.connect(self._onApplicationStateChanged)
        cfg.customThemeMode.valueChanged.connect(self._onThemeModeChanged)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._onSystemColorSchemeChanged)
        qconfig.themeChanged.connect(self.update)
        qconfig.themeChanged.connect(lambda *_: IconBodyLabel.clearCache())

    def _onThemeModeChanged(self, mode: str):
        setTheme(toQFluentTheme(mode), save=False)

    def _onSystemColorSchemeChanged(self, colorScheme: Qt.ColorScheme):
        if cfg.customThemeMode.value != "System":
            return
        if colorScheme == Qt.ColorScheme.Dark:
            setTheme(Theme.DARK, save=False)
        elif colorScheme == Qt.ColorScheme.Light:
            setTheme(Theme.LIGHT, save=False)
        else:
            setTheme(Theme.AUTO, save=False)

    def _onApplicationStateChanged(self, state: Qt.ApplicationState):
        if state == Qt.ApplicationState.ApplicationActive:
            self._updatePermissionBanner()

    def _updatePermissionBanner(self):
        self.permissionBanner.setVisible(not isStorageGranted())

    def _updateAddButtonVisibility(self):
        onTaskPage = self.stackedWidget.currentIndex() == 0
        self.addButton.setVisible(onTaskPage and not self.taskPage.isSelectionMode)

    def addPage(self, page: QWidget, icon: FluentIcon, text: str) -> QWidget:
        self.stackedWidget.addWidget(page)
        self.navigationBar.addItem(icon, text)
        return page

    def showAddTaskDialog(self):
        if not isStorageGranted():
            requestStoragePermission()
            InfoBar.warning(
                self.tr("需要存储权限"),
                self.tr("请在系统设置授予「所有文件访问」后再新建任务"),
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        from app.view.mobile.add_task_dialog import MobileAddTaskDialog

        dialog = MobileAddTaskDialog.initialize(self)

        dialog.widget.setFixedWidth(min(700, self.width() - 24))
        if dialog.isVisible() and not dialog.isStandaloneMode:
            dialog.raise_()
            dialog.activateWindow()
            return
        dialog.showMask()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 16
        self.addButton.move(
            self.width() - self.addButton.width() - margin,
            self.height() - self.navigationBar.height() - self.addButton.height() - margin,
        )

    def addTask(self, task) -> bool:
        try:
            taskService.addTask(task)
            coreService.createTask(task)
            return True
        except Exception as e:
            logger.opt(exception=e).error("无法创建任务卡片 {}", task.title)
            return False

    @staticmethod
    def updateThemeColor():
        palette = QApplication.palette()

        for role in (QPalette.ColorRole.Accent, QPalette.ColorRole.Highlight):
            color = palette.color(role)
            if not color.isValid() or cfg.themeColor.value == color:
                continue

            setThemeColor(color, save=False)
            return

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(32, 32, 32) if isDarkTheme() else QColor(243, 243, 243))
