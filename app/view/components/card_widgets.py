from typing import Any

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor, QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from qfluentwidgets import ScrollArea, setFont, isDarkTheme

from app.bases.models import Task
from app.view.components.cards import ResultCard, ParseSettingCard


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
        self.scrollLayout.addWidget(widget, alignment=Qt.AlignmentFlag.AlignTop)

    def setTitle(self, title: str):
        self.headerLabel.setText("    " + title)


class ParseResultHeaderCardWidget(HeaderCardWidgetBase):
    """解析结果标题栏组件"""
    defaultCardHeight = 35
    minimumVisibleCards = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle(self.tr("解析结果"))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

    def _cardWidgets(self) -> list[ResultCard]:
        cards: list[ResultCard] = []
        for i in range(self.scrollLayout.count()):
            widget = self.scrollLayout.itemAt(i).widget()
            if isinstance(widget, ResultCard):
                cards.append(widget)
        return cards

    def _cardDisplayHeight(self, card: ResultCard) -> int:
        return card.height() or card.sizeHint().height() or self.defaultCardHeight

    def _cardsTotalHeight(self, cards: list[ResultCard]) -> int:
        return sum(self._cardDisplayHeight(card) for card in cards)

    def _widgetChromeHeight(self) -> int:
        margins = self.contentsMargins()
        viewportMargins = self.scrollArea.viewportMargins()
        return (
            margins.top()
            + margins.bottom()
            + self.headerLabel.height()
            + self.scrollArea.frameWidth() * 2
            + viewportMargins.top()
            + viewportMargins.bottom()
        )

    def _sizeHintForContentHeight(self, contentHeight: int) -> QSize:
        size = super().sizeHint()
        height = self._widgetChromeHeight() + contentHeight
        return QSize(size.width(), height)

    def minimumSizeHint(self) -> QSize:
        cards = self._cardWidgets()
        return self._sizeHintForContentHeight(
            self._cardsTotalHeight(cards[:self.minimumVisibleCards])
        )

    def maximumSizeHint(self) -> QSize:
        return self._sizeHintForContentHeight(self._cardsTotalHeight(self._cardWidgets()))

    def sizeHint(self) -> QSize:
        return self.maximumSizeHint().expandedTo(self.minimumSizeHint())

    def clearResults(self):
        """清空所有解析结果"""
        while self.scrollLayout.count():
            child = self.scrollLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.updateGeometry()

    def getAllTasks(self) -> list[Task]:
        """获取所有解析结果的数据"""
        results = []
        for i in range(self.scrollLayout.count()):
            widget = self.scrollLayout.itemAt(i).widget()
            if isinstance(widget, ResultCard):
                results.append(widget.getTask())
        return results


class ParseSettingHeaderCardWidget(HeaderCardWidgetBase):
    """解析设置标题栏组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle(self.tr("下载设置"))
        self.cards: list[ParseSettingCard] = []

    def addCard(self, card: ParseSettingCard):
        if not isinstance(card, ParseSettingCard):
            raise TypeError("card must be GroupSettingCard")

        self.cards.append(card)
        self.scrollLayout.addWidget(card)

    @property
    def payload(self) -> dict[str, Any]:
        return {k: v for card in self.cards for k, v in card.payload.items()}
