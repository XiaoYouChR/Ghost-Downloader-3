from PySide6.QtCore import QSize
from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import PlainTextEdit


class AutoSizingEdit(PlainTextEdit):
    def __init__(self, parent=None, minimumVisibleLines: int = 5):
        super().__init__(parent)
        self._minimumVisibleLines = minimumVisibleLines
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.document().blockCountChanged.connect(self.updateGeometry)

    def _lineHeight(self) -> int:
        return self.fontMetrics().lineSpacing()

    def _editorChromeHeight(self) -> int:
        margins = self.contentsMargins()
        viewportMargins = self.viewportMargins()
        documentMargin = round(self.document().documentMargin() * 2)
        return (
            margins.top()
            + margins.bottom()
            + viewportMargins.top()
            + viewportMargins.bottom()
            + self.frameWidth() * 2
            + documentMargin
        )

    def _sizeHintForLineCount(self, lineCount: int) -> QSize:
        size = super().sizeHint()
        height = self._editorChromeHeight() + self._lineHeight() * lineCount
        return QSize(size.width(), height)

    def minimumSizeHint(self) -> QSize:
        return self._sizeHintForLineCount(min(self._minimumVisibleLines, self.document().blockCount()))

    def maximumSizeHint(self) -> QSize:
        return self._sizeHintForLineCount(self.document().blockCount())

    def sizeHint(self) -> QSize:
        return self.maximumSizeHint().expandedTo(self.minimumSizeHint())
