from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from qfluentwidgets import ScrollArea, setFont, isDarkTheme, CardGroupWidget

from app.view.components.cards import ResultCard, GroupSettingCard


class HeaderCardWidgetBase(QWidget):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.borderRadius = 5

        self.viewLayout = QVBoxLayout(self)
        self.headerLabel = QLabel(self)

        self.scrollArea = ScrollArea(self)
        self.scrollWidget = QWidget(self)
        self.scrollLayout = QVBoxLayout(self.scrollWidget)

        self.initWidget()
        self.initLayout()

    def initWidget(self):
        setFont(self.headerLabel, 15, QFont.Weight.DemiBold)
        self.headerLabel.setFixedHeight(30)
        self.headerLabel.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.enableTransparentBackground()

    def initLayout(self):
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.setSpacing(0)
        self.viewLayout.addWidget(self.headerLabel)
        self.viewLayout.addWidget(self.scrollArea)

        self.scrollLayout.setContentsMargins(0, 0, 0, 0)
        self.scrollLayout.setSpacing(0)

    @property
    def backgroundColor(self):
        return QColor(255, 255, 255, 13 if isDarkTheme() else 200)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.backgroundColor)

        if isDarkTheme():
            painter.setPen(QColor(0, 0, 0, 96))
        else:
            painter.setPen(QColor(0, 0, 0, 24))

        r = self.borderRadius
        # painter.drawLine(self.rect().topLeft() + QPoint(0, 30), self.rect().topRight() + QPoint(0, 30))
        painter.drawRoundedRect(self.rect(), r, r)

    def addWidget(self, widget):
        self.scrollLayout.addWidget(widget)

    def setTitle(self, title: str):
        self.headerLabel.setText("    " + title)


class ParseResultHeaderCardWidget(HeaderCardWidgetBase):
    """解析结果标题栏组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("解析结果")

    def clearResults(self):
        """清空所有解析结果"""
        while self.scrollLayout.count():
            child = self.scrollLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def getAllResults(self) -> list:
        """获取所有解析结果的数据"""
        results = []
        for i in range(self.scrollLayout.count()):
            widget = self.scrollLayout.itemAt(i).widget()
            if isinstance(widget, ResultCard):
                results.append(widget.getData())
        return results


class SettingHeaderCardWidget(HeaderCardWidgetBase):
    """设置标题栏组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("下载设置")

    def addGroup(self, icon, title: str, widget: QWidget, stretch=0) -> GroupSettingCard:
        """ add widget to a new group

        Parameters
        ----------
        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        widget: QWidget
            the widget to be added

        stretch: int
            the layout stretch of widget
        """
        group = GroupSettingCard(icon, title, self)
        group.addWidget(widget, stretch=stretch)

        self.scrollLayout.addWidget(group)

        return group
