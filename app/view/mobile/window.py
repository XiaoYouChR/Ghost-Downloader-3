"""移动端主窗口 —— QWidget 壳, 不继承 MainWindow/MSFluentWindow(后者锁死左侧竖栏), 用 QStackedWidget + 自建底部导航。"""

from pathlib import Path

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
from app.services.category_service import categoryService
from app.services.core_service import coreService
from app.services.task_service import taskService
from app.supports.android import isStorageGranted, requestStoragePermission
from app.supports.config import cfg, toQFluentTheme
from app.supports.utils import deduplicateFilename
from app.view.components.labels import IconBodyLabel
from app.view.mobile.navigation import BottomNavigationBar
from app.view.mobile.permission import PermissionBanner
from app.view.mobile.setting_page import MobileSettingPage
from app.view.mobile.task_page import MobileTaskPage


class MobileMainWindow(QWidget):

    def __init__(self):
        super().__init__(parent=None)
        self.updateThemeColor()
        BrowserService.initialize(self)  # SettingPage 建页要读 pairToken, 须先就绪
        self.stackedWidget = QStackedWidget(self)
        self.navigationBar = BottomNavigationBar(self)
        self.vBoxLayout = QVBoxLayout(self)
        self.permissionBanner = PermissionBanner(requestStoragePermission, self)
        self.taskPage = MobileTaskPage(self, onSelectionModeChanged=self._refreshAddButton)
        self.settingPage = MobileSettingPage(self)
        self.addButton = PrimaryToolButton(FluentIcon.ADD, self)  # 新建任务 FAB, 浮于任务页右下
        self._initWidget()
        self._initLayout()
        self._bind()
        self._refreshPermissionGate()

    def _initWidget(self):
        self.setObjectName("MobileMainWindow")
        self.setWindowIcon(QIcon(":/image/logo.png"))
        self.setWindowTitle("Ghost Downloader")
        self.taskPage.setObjectName("taskInterface")
        self.settingPage.setObjectName("settingInterface")
        self.addButton.setFixedSize(56, 56)
        self.addButton.setIconSize(QSize(22, 22))
        self.addButton.raise_()
        self.addSubInterface(self.taskPage, FluentIcon.DOWNLOAD, self.tr("任务"))
        self.addSubInterface(self.settingPage, FluentIcon.SETTING, self.tr("设置"))

    def _initLayout(self):
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.permissionBanner, 0)
        self.vBoxLayout.addWidget(self.stackedWidget, 1)
        self.vBoxLayout.addWidget(self.navigationBar, 0)

    def _bind(self):
        self.navigationBar.currentChanged.connect(self.stackedWidget.setCurrentIndex)
        self.navigationBar.currentChanged.connect(lambda *_: self._refreshAddButton())
        self.addButton.clicked.connect(self.showAddTaskDialog)
        QApplication.instance().applicationStateChanged.connect(self._onApplicationStateChanged)
        cfg.customThemeMode.valueChanged.connect(self._onThemeModeChanged)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._onSystemColorSchemeChanged)
        qconfig.themeChanged.connect(self.update)
        qconfig.themeChanged.connect(lambda *_: IconBodyLabel.clearCache())  # 缓存按 id 不分主题, 切主题须清否则图标留旧色

    def _onThemeModeChanged(self, mode: str):
        # "System"→AUTO 重解析当前系统深浅, "Light"/"Dark" 锁定不跟随系统
        setTheme(toQFluentTheme(mode), save=False)

    def _onSystemColorSchemeChanged(self, colorScheme: Qt.ColorScheme):
        if cfg.customThemeMode.value != "System":  # 仅"跟随系统"时跟随系统深浅切换
            return
        if colorScheme == Qt.ColorScheme.Dark:
            setTheme(Theme.DARK, save=False)
        elif colorScheme == Qt.ColorScheme.Light:
            setTheme(Theme.LIGHT, save=False)
        else:
            setTheme(Theme.AUTO, save=False)

    def _onApplicationStateChanged(self, state: Qt.ApplicationState):
        # onResume 复检权限, 收起 banner
        if state == Qt.ApplicationState.ApplicationActive:
            self._refreshPermissionGate()

    def _refreshPermissionGate(self):
        self.permissionBanner.setVisible(not isStorageGranted())

    def _refreshAddButton(self):
        # FAB 仅任务页且非多选时露面, 否则与右下多选命令栏撞位
        onTaskPage = self.stackedWidget.currentIndex() == 0
        self.addButton.setVisible(onTaskPage and not self.taskPage.isSelectionMode)

    def addSubInterface(self, interface: QWidget, icon: FluentIcon, text: str) -> QWidget:
        self.stackedWidget.addWidget(interface)
        self.navigationBar.addItem(icon, text)
        return interface

    def showAddTaskDialog(self):
        if not isStorageGranted():  # 软门: 未授权拦截新建, 跳设置页引导
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
        # 桌面固定 700px 在手机会溢出, 压到窗宽内
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
