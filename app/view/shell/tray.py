import sys
from enum import Enum

from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMenu, QSystemTrayIcon
from qfluentwidgets import (
    Action, FluentIcon, FluentIconBase, FluentStyleSheet, RoundMenu, Theme,
    getIconColor, isDarkTheme,
)

from app.format import toReadableSize
from app.services.speed_meter import speedMeter
from app.services.task_service import taskService
from app.signal_bus import signalBus


class GhostIcon(FluentIconBase, Enum):
    GHOST = "ghost"

    def path(self, theme=Theme.AUTO) -> str:
        return ":/image/logo_menubar_template.png"

    def _toTintedPixmap(self, theme: Theme) -> QPixmap:
        pixmap = QPixmap(self.path())
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(getIconColor(theme)))
        painter.end()
        return pixmap

    def icon(self, theme=Theme.AUTO, color=None) -> QIcon:
        return QIcon(self._toTintedPixmap(theme))

    def render(self, painter, rect, theme=Theme.AUTO, indexes=None, **attributes) -> None:
        painter.drawPixmap(QRectF(rect).toRect(), self._toTintedPixmap(theme))


if sys.platform == "win32":
    from typing import TYPE_CHECKING

    from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory
    from qfluentwidgets.common.screen import getCurrentScreenGeometry
    from qfluentwidgets.components.widgets.menu import MenuActionListWidget
    from qframelesswindow import WindowEffect

    if TYPE_CHECKING:
        from PySide6.QtGui import QAction

    class MenuStyle(QProxyStyle):

        def __init__(self, iconSize=14):
            super().__init__()
            self._iconSize = iconSize

        def pixelMetric(self, metric, option, widget):
            if metric == QStyle.PixelMetric.PM_SmallIconSize:
                return self._iconSize
            return super().pixelMetric(metric, option, widget)

        def polish(self, app, /):
            QStyleFactory.create("fusion").polish(app)

        def unpolish(self, app, /):
            QStyleFactory.create("fusion").polish(app)

    class AcrylicMenu(RoundMenu):

        def __init__(self, title="", parent=None):
            QMenu.__init__(self, parent)
            self.setTitle(title)
            self._icon = QIcon()
            self._actions: list[QAction] = []
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

            self._initWidget()
            self._initLayout()
            self._bind()

        def _initWidget(self) -> None:
            self.setWindowFlags(
                Qt.WindowType.Popup
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.NoDropShadowWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setMouseTracking(True)
            self.setStyle(MenuStyle())
            self.timer.setSingleShot(True)
            self.timer.setInterval(400)

        def _initLayout(self) -> None:
            self.hBoxLayout.addWidget(self.view, 1, Qt.AlignmentFlag.AlignCenter)
            self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
            FluentStyleSheet.MENU.apply(self)
            self.view.setProperty("transparent", True)

        def _bind(self) -> None:
            self.timer.timeout.connect(self._onShowMenuTimeOut)
            self.view.itemClicked.connect(self._onItemClicked)
            self.view.itemEntered.connect(self._onItemEntered)

        def adjustPosition(self) -> None:
            m = self.hBoxLayout.contentsMargins()
            rect = getCurrentScreenGeometry()
            w = self.hBoxLayout.sizeHint().width() + 5
            x = min(self.x() - m.left(), rect.right() - w)
            y = self.y() - 45
            self.move(x, y)

        def showEvent(self, event):
            self.windowEffect.addMenuShadowEffect(self.winId())
            self.windowEffect.addShadowEffect(self.winId())
            self.windowEffect.enableBlurBehindWindow(self.winId())
            from app.config.cfg import cfg
            dark = isDarkTheme() if cfg.themeMode.value == Theme.AUTO else cfg.themeMode.value == Theme.DARK
            self.windowEffect.setAcrylicEffect(
                self.winId(),
                "00000030" if dark else "FFFFFF30",
            )
            # 无 parent 时 fontMetrics 在首次显示前不准，基于正确屏幕重算
            for action in self._actions:
                item = action.property('item')
                if item:
                    self._adjustItemText(item, action)
            self.view.adjustSize()
            self.adjustSize()
            self.adjustPosition()
            self.raise_()
            self.activateWindow()
            self.setFocus()
            return super().showEvent(event)

        def paintEvent(self, e) -> None:
            painter = QPainter(self)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 1))
            painter.drawRect(self.rect())

    TrayMenu = AcrylicMenu
else:
    TrayMenu = RoundMenu


class SystemTrayIcon(QSystemTrayIcon):
    NAME = "Ghost Downloader"

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(icon, parent)
        self.setToolTip(self.NAME)

        self._menu = TrayMenu()
        self._menu.addAction(Action(GhostIcon.GHOST, self.tr("仪表盘"), self._menu,
                                    triggered=lambda: signalBus.activationRequested.emit()))
        self._menu.addAction(Action(FluentIcon.PLAY, self.tr("全部开始"), self._menu,
                                    triggered=taskService.startAll))
        self._menu.addAction(Action(FluentIcon.PAUSE, self.tr("全部暂停"), self._menu,
                                    triggered=taskService.pauseAll))
        self._menu.addSeparator()
        self._menu.addAction(Action(FluentIcon.CLOSE, self.tr("退出程序"), self._menu,
                                    triggered=QApplication.instance().quit))
        self.setContextMenu(self._menu)
        self.destroyed.connect(self._menu.deleteLater)

        self.activated.connect(self._onActivated)
        self.messageClicked.connect(signalBus.activationRequested)
        speedMeter.speedChanged.connect(self._onSpeedChanged)

    def _onActivated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            signalBus.activationRequested.emit()

    def _onSpeedChanged(self, speed: int) -> None:
        if speed > 0:
            self.setToolTip(f"{self.NAME}\n↓ {toReadableSize(speed)}/s")
        else:
            self.setToolTip(self.NAME)
