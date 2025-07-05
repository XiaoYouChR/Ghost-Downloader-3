from PySide6.QtCore import QSize, QRect, QTimer
from PySide6.QtGui import QPainter, Qt, QIcon
from PySide6.QtWidgets import QWidget, QHBoxLayout, QStyleFactory, QStyle, QProxyStyle, QMenu
from qfluentwidgets import BodyLabel, FluentIconBase, drawIcon, ProgressBar, RoundMenu, FluentStyleSheet
from qfluentwidgets.components.widgets.menu import MenuActionListWidget
from qframelesswindow import WindowEffect


# 我是傻逼
# class DisabledRichTextEdit(TextEdit):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#
#     def copy(self):
#         # 仅复制纯文本到剪贴板
#         clipboard = QApplication.clipboard()
#         clipboard.setText(self.toPlainText())  # 使用纯文本格式
#
#     def paste(self):
#         # 仅粘贴纯文本
#         clipboard = QApplication.clipboard()
#         text = clipboard.text().replace(" ", "")  # 获取纯文本内容并去除空格
#         self.insertPlainText(text)  # 使用 insertPlainText 插入纯文本
#
#     def keyPressEvent(self, event):
#         if event.modifiers() == Qt.ControlModifier:
#             if event.key() == Qt.Key_C:
#                 self.copy()
#                 event.accept()  # 阻止默认复制操作
#             elif event.key() == Qt.Key_V:
#                 self.paste()
#                 event.accept()  # 阻止默认粘贴操作
#             else:
#                 super().keyPressEvent(event)
#         else:
#             super().keyPressEvent(event)


class IconBodyLabel(BodyLabel):
    def __init__(self, text:str, icon: FluentIconBase, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.icon = icon
        self.setContentsMargins(20, 0, 0, 2)  # 给 Icon 和 Text 之间留出 4px 的间距
        self.iconSize = QSize(16, 16)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing |
                               QPainter.SmoothPixmapTransform)

        # 绘制图标
        iconHeight, iconWidth = self.iconSize.height(), self.iconSize.width()
        iconRect = QRect(0, (self.height() - iconHeight) // 2, iconWidth, iconHeight)
        drawIcon(self.icon, painter, iconRect)


class TaskProgressBar(QWidget):
    def __init__(self, blockNum: int, parent=None):
        super().__init__(parent)

        self.blockNum = blockNum
        self.progressBarList = []

        # Setup UI
        self.HBoxLayout = QHBoxLayout(self)
        self.HBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.HBoxLayout.setSpacing(0)
        self.setLayout(self.HBoxLayout)

        for i in range(self.blockNum):
            _ = ProgressBar(self)
            self.HBoxLayout.addWidget(_)
            self.progressBarList.append(_)

    def addProgressBar(self, content: list, quantity: int):

        for i in range(quantity):
            _ = ProgressBar(self)
            self.HBoxLayout.addWidget(_)
            self.progressBarList.append(_)

        self.blockNum += quantity

        for e, i in enumerate(content):  # 更改 Stretch
            self.HBoxLayout.setStretch(e, int((i["end"] - i["start"]) / 1048576))  # 除以1MB

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

    def pixelMetric(self, metric, option, widget):
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
                            Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowStaysOnTopHint)
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
