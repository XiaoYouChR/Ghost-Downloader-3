from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QHBoxLayout, QSystemTrayIcon
from qfluentwidgets import RoundMenu, FluentStyleSheet, isDarkTheme, Action, FluentIcon
from qfluentwidgets.common.screen import getCurrentScreenGeometry
from qfluentwidgets.components.widgets.menu import MenuActionListWidget, CustomMenuStyle
from qframelesswindow import WindowEffect

from app.supports.config import cfg
from app.supports.signal_bus import signalBus

if TYPE_CHECKING:
    from PySide6.QtGui import QAction
    from app.view.windows.main_window import MainWindow


class AcrylicMenu(RoundMenu):
    """Win32API 绘制 Acrylic/Aero Menu"""

    def __init__(self, title="", parent=None):
        QMenu.__init__(self, parent)
        self.setTitle(title)
        self._icon = QIcon()
        self._actions:list["QAction"] = []
        self._subMenus = []

        self.isSubMenu = False
        self.parentMenu = None
        self.menuItem = None
        self.lastHoverItem = None
        self.lastHoverSubMenuItem = None
        self.isHideBySystem = True
        self.itemHeight = 28

        self.hBoxLayout = QHBoxLayout(self)
        self.view = MenuActionListWidget(self)
        self.windowEffect = WindowEffect(self)

        self.aniManager = None
        self.timer = QTimer(self)

        self.__initWidgets()

    def __initWidgets(self):
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self.setStyle(CustomMenuStyle())

        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._onShowMenuTimeOut)

        self.hBoxLayout.addWidget(self.view, 1, Qt.AlignmentFlag.AlignCenter)

        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        FluentStyleSheet.MENU.apply(self)
        self.view.setProperty("transparent", True)

        self.view.itemClicked.connect(self._onItemClicked)
        self.view.itemEntered.connect(self._onItemEntered)

    def adjustPosition(self):
        m = self.hBoxLayout.contentsMargins()
        rect = getCurrentScreenGeometry()
        w, h = (
            self.hBoxLayout.sizeHint().width() + 5,
            self.hBoxLayout.sizeHint().height(),
        )

        x = min(self.x() - m.left(), rect.right() - w)
        y = self.y() - 45

        self.move(x, y)

    def showEvent(self, event):
        self.windowEffect.addMenuShadowEffect(self.winId())
        self.windowEffect.addShadowEffect(self.winId())
        self.windowEffect.enableBlurBehindWindow(self.winId())
        self.windowEffect.setAcrylicEffect(
            self.winId(),
            (
                "00000030"
                if (
                    isDarkTheme()
                    if cfg.customThemeMode.value == "System"
                    else cfg.customThemeMode.value == "Dark"
                )
                else "FFFFFF30"
            ),
        )

        self.adjustPosition()
        self.raise_()
        self.activateWindow()
        self.setFocus()

        return super().showEvent(event)


class SystemTrayIcon(QSystemTrayIcon):

    def __init__(self, parent: "MainWindow" = None):
        super().__init__(parent=parent)
        self.setIcon(parent.windowIcon())
        self.setToolTip('Ghost Downloader 🥰')

        self.menu = AcrylicMenu(parent=parent)

        self.showAction = Action(QIcon(":/image/logo_withoutBackground.png"), self.tr('仪表盘'), self.menu)
        self.showAction.triggered.connect(self._onShowActionTriggered)
        self.menu.addAction(self.showAction)

        self.allStartAction = Action(FluentIcon.PLAY, self.tr('全部开始'), self.menu)
        self.allStartAction.triggered.connect(self._onAllStartActionTriggered)
        self.menu.addAction(self.allStartAction)

        self.allPauseAction = Action(FluentIcon.PAUSE, self.tr('全部暂停'), self.menu)
        self.allPauseAction.triggered.connect(self._onAllPauseActionTriggered)
        self.menu.addAction(self.allPauseAction)

        self.quitAction = Action(FluentIcon.CLOSE, self.tr('退出程序'), self.menu)
        self.quitAction.triggered.connect(self._onQuitActionTriggered)
        self.menu.addAction(self.quitAction)

        self.setContextMenu(self.menu)

        self.activated.connect(self.onTrayIconClick)
        self.messageClicked.connect(self._onShowActionTriggered)

    def _onShowActionTriggered(self):
        signalBus.showMainWindow.emit()

    def _onAllStartActionTriggered(self):
        window = self.parent()
        taskPage = getattr(window, "taskPage", None)
        if taskPage is not None:
            taskPage.startAllTasks()

    def _onAllPauseActionTriggered(self):
        window = self.parent()
        taskPage = getattr(window, "taskPage", None)
        if taskPage is not None:
            taskPage.pauseAllTasks()

    def _onQuitActionTriggered(self):
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def onTrayIconClick(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._onShowActionTriggered()
