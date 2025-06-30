from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory, QMenu, QHBoxLayout
from qfluentwidgets import RoundMenu, FluentStyleSheet
from qfluentwidgets.components.widgets.menu import MenuActionListWidget
from qframelesswindow import WindowEffect


class CustomMenuStyle(QProxyStyle):
    """ Custom menu style """

    def __init__(self, iconSize=14):
        """
        Parameters
        ----------
        iconSizeL int
            the size of icon
        """
        super().__init__()
        self.iconSize = iconSize

    def pixelMetric(self, metric, /, option = ..., widget = ...):
        if metric == QStyle.PixelMetric.PM_SmallIconSize:
            return self.iconSize

        return super().pixelMetric(metric, option, widget)

    def polish(self, app, /):
        QStyleFactory.create("fusion").polish(app)

    def unpolish(self, app, /):
        QStyleFactory.create("fusion").polish(app)


class CustomAcrylicMenu(RoundMenu):
    """ Win32API 绘制 Acrylic/Aero Menu """

    def __init__(self, title="", parent=None):
        QMenu.__init__(self, parent)
        self.setTitle(title)
        self._icon = QIcon()
        self._actions = []  # type: List[QAction]
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
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.NoDropShadowWindowHint)
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

    def showEvent(self, event, /):
        self.windowEffect.addMenuShadowEffect(self.winId())
        self.windowEffect.addShadowEffect(self.winId())
        self.windowEffect.enableBlurBehindWindow(self.winId())
        self.windowEffect.setAcrylicEffect(self.winId())

        super().showEvent(event)
