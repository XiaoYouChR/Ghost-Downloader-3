from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QWidget, QVBoxLayout, QLabel, QSizePolicy
from qfluentwidgets import CaptionLabel, setFont, isDarkTheme

from app.view.components.scroll_area import ScrollArea

from app.format import toReadableSize


class TitledCardGroup(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.headerLabel = QLabel(self)
        self.scrollArea = ScrollArea(self)
        self.scrollWidget = QWidget(self)
        self.scrollLayout = QVBoxLayout(self.scrollWidget)

        setFont(self.headerLabel, 15, QFont.Weight.DemiBold)
        self.headerLabel.setFixedHeight(30)
        self.headerLabel.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.enableTransparentBackground()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.headerLabel)
        layout.addWidget(self.scrollArea)
        self.scrollLayout.setContentsMargins(0, 0, 0, 0)
        self.scrollLayout.setSpacing(0)

    def setTitle(self, title: str) -> None:
        self.headerLabel.setText("    " + title)

    def addCard(self, card: QWidget) -> None:
        self.scrollLayout.addWidget(card, alignment=Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, e) -> None:
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(255, 255, 255, 13 if isDarkTheme() else 200))
        painter.setPen(QColor(0, 0, 0, 96 if isDarkTheme() else 24))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 5, 5)


class DraftCardGroup(TitledCardGroup):
    CARD_HEIGHT = 35
    MIN_VISIBLE = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cardByUrl: dict[str, QWidget] = {}

        self._ratioLabel = CaptionLabel("", self)
        self._ratioLabel.setTextColor(QColor(196, 53, 1), QColor(252, 169, 3))
        self._sizeLabel = CaptionLabel("", self)
        for label in (self._ratioLabel, self._sizeLabel):
            setFont(label, 13)
            label.setFixedHeight(30)
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            label.hide()

        self._rightPad = QLabel("  ", self)
        setFont(self._rightPad, 15, QFont.Weight.DemiBold)
        self._rightPad.setFixedHeight(30)

        self.layout().removeWidget(self.headerLabel)
        headerRow = QHBoxLayout()
        headerRow.setContentsMargins(0, 0, 0, 0)
        headerRow.setSpacing(8)
        headerRow.addWidget(self.headerLabel, 1)
        headerRow.addWidget(self._ratioLabel)
        headerRow.addWidget(self._sizeLabel)
        headerRow.addWidget(self._rightPad)
        self.layout().insertLayout(0, headerRow)

        self.setTitle(self.tr("解析结果"))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def updateStats(self, successCount: int, failCount: int, totalSize: int) -> None:
        totalCount = successCount + failCount
        if totalCount == 0:
            self._ratioLabel.hide()
            self._sizeLabel.hide()
            return

        if failCount > 0:
            self._ratioLabel.setText(f"{successCount}/{totalCount}")
            self._ratioLabel.show()
        else:
            self._ratioLabel.hide()

        if totalSize > 0:
            self._sizeLabel.setText(toReadableSize(totalSize))
            self._sizeLabel.show()
        elif successCount > 0:
            self._sizeLabel.setText(self.tr("{0} 个任务").format(successCount))
            self._sizeLabel.show()
        else:
            self._sizeLabel.hide()

    def addCard(self, url: str, card: QWidget) -> None:
        self._cardByUrl[url] = card
        super().addCard(card)
        self.updateGeometry()

    def setUrls(self, urls: list[str]) -> None:
        keep = set(urls)
        for url in list(self._cardByUrl):
            if url not in keep:
                card = self._cardByUrl.pop(url)
                self.scrollLayout.removeWidget(card)
                card.deleteLater()
        for i, url in enumerate(u for u in urls if u in self._cardByUrl):
            card = self._cardByUrl[url]
            if self.scrollLayout.indexOf(card) != i:
                self.scrollLayout.insertWidget(i, card, alignment=Qt.AlignmentFlag.AlignTop)
        self.updateGeometry()

    def clear(self) -> None:
        while self.scrollLayout.count():
            child = self.scrollLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._cardByUrl.clear()
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        cards = self._cards()
        content = sum(self._cardHeight(c) for c in cards)
        minimum = sum(self._cardHeight(c) for c in cards[:self.MIN_VISIBLE])
        padding = self._paddingHeight()
        size = super().sizeHint()
        return QSize(size.width(), max(padding + minimum, padding + content))

    def minimumSizeHint(self) -> QSize:
        cards = self._cards()
        content = sum(self._cardHeight(c) for c in cards[:self.MIN_VISIBLE])
        size = super().sizeHint()
        return QSize(size.width(), self._paddingHeight() + content)

    def _cards(self) -> list[QWidget]:
        return [
            self.scrollLayout.itemAt(i).widget()
            for i in range(self.scrollLayout.count())
            if self.scrollLayout.itemAt(i).widget()
        ]

    def _cardHeight(self, card: QWidget) -> int:
        return card.height() or card.sizeHint().height() or self.CARD_HEIGHT

    def _paddingHeight(self) -> int:
        m = self.contentsMargins()
        vm = self.scrollArea.viewportMargins()
        return m.top() + m.bottom() + self.headerLabel.height() + self.scrollArea.frameWidth() * 2 + vm.top() + vm.bottom()


class OptionCardGroup(TitledCardGroup):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle(self.tr("下载设置"))
        self._cards: list[QWidget] = []

    def addCard(self, card: QWidget) -> None:
        self._cards.append(card)
        super().addCard(card)

    def insertCard(self, index: int, card: QWidget) -> None:
        self._cards.insert(index, card)
        self.scrollLayout.insertWidget(index, card, alignment=Qt.AlignmentFlag.AlignTop)

    def options(self) -> dict:
        result = {}
        for card in self._cards:
            result.update(card.options())
        return result

    def reset(self) -> None:
        for card in self._cards:
            card.reset()
