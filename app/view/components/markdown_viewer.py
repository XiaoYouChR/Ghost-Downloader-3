from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QTextBrowser, QSizePolicy


class MarkdownViewer(QTextBrowser):

    def __init__(self, parent=None, minimumVisibleLines: int = 5, maximumVisibleLines: int = 16):
        super().__init__(parent)
        self._minimumVisibleLines = minimumVisibleLines
        self._maximumVisibleLines = maximumVisibleLines

        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.document().contentsChanged.connect(self.updateGeometry)
        self.anchorClicked.connect(QDesktopServices.openUrl)

    def setMarkdown(self, text: str) -> None:
        self.document().setMarkdown(text)

    def minimumSizeHint(self) -> QSize:
        lineHeight = self.fontMetrics().lineSpacing()
        padding = self.contentsMargins().top() + self.contentsMargins().bottom() + self.frameWidth() * 2
        return QSize(super().sizeHint().width(), padding + lineHeight * self._minimumVisibleLines)

    def sizeHint(self) -> QSize:
        lineHeight = self.fontMetrics().lineSpacing()
        padding = self.contentsMargins().top() + self.contentsMargins().bottom() + self.frameWidth() * 2
        maxHeight = padding + lineHeight * self._maximumVisibleLines
        docHeight = int(self.document().size().height()) + padding
        return QSize(super().sizeHint().width(), min(docHeight, maxHeight)).expandedTo(self.minimumSizeHint())
