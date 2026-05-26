from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QKeyEvent, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QWidget,
)
from qfluentwidgets import FlowLayout, PlainTextEdit, TransparentToolButton
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.common.color import autoFallbackThemeColor
from qfluentwidgets.common.font import setFont
from qfluentwidgets.common.icon import isDarkTheme


class AutoSizingEdit(PlainTextEdit):
    def __init__(
        self,
        parent=None,
        minimumVisibleLines: int = 5,
        maximumVisibleLines: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._minimumVisibleLines = minimumVisibleLines
        self._maximumVisibleLines = maximumVisibleLines
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

    def _visibleLineCount(self) -> int:
        lineCount = self.document().blockCount()
        if self._maximumVisibleLines is None:
            return lineCount
        return min(lineCount, self._maximumVisibleLines)

    def minimumSizeHint(self) -> QSize:
        return self._sizeHintForLineCount(
            min(self._minimumVisibleLines, self.document().blockCount())
        )

    def maximumSizeHint(self) -> QSize:
        return self._sizeHintForLineCount(self._visibleLineCount())

    def sizeHint(self) -> QSize:
        return self.maximumSizeHint().expandedTo(self.minimumSizeHint())


class _TokenWidget(QWidget):

    closeClicked = Signal(QWidget)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text

        self.label = QLabel(self)
        self.closeButton = TransparentToolButton(FIF.CLOSE, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.label.setText(self._text)
        setFont(self.label)
        self.closeButton.setFixedSize(20, 20)
        self.closeButton.setIconSize(QSize(8, 8))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(24)

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(2)
        layout.addWidget(self.label)
        layout.addWidget(self.closeButton)

    def _bind(self) -> None:
        self.closeButton.clicked.connect(lambda: self.closeClicked.emit(self))

    def text(self) -> str:
        return self._text

    def elide(self, maxWidth: int) -> None:
        fm = QFontMetrics(self.label.font())
        available = maxWidth - 8 - 4 - 2 - self.closeButton.width()
        elided = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, available)
        self.label.setText(elided)
        self.setMaximumWidth(maxWidth)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if isDarkTheme():
            painter.setBrush(QColor(255, 255, 255, 20))
        else:
            painter.setBrush(QColor(0, 0, 0, 12))
        painter.drawRoundedRect(self.rect(), 4, 4)


class _TokenInput(QLineEdit):

    submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrame(False)
        self.setStyleSheet("QLineEdit { background: transparent; border: none; }")
        setFont(self)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.IBeamCursor)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            text = self.text().strip()
            if text:
                self.submitted.emit(text)
                self.clear()
            return
        super().keyPressEvent(event)


class TokenLineEdit(QWidget):

    tokensChanged = Signal(list)

    def __init__(self, parent=None, *, maxTokenCount: int = 0):
        super().__init__(parent)
        self._tokens: list[str] = []
        self._tokenWidgets: list[_TokenWidget] = []
        self._maxTokenCount = maxTokenCount
        self._hasFocus = False

        self.flowLayout = FlowLayout(self, needAni=False, isTight=True)
        self.lineEdit = _TokenInput(self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setMinimumHeight(33)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.lineEdit.setPlaceholderText(self.tr("添加..."))
        self.lineEdit.installEventFilter(self)

    def _initLayout(self) -> None:
        self.flowLayout.setContentsMargins(4, 4, 4, 4)
        self.flowLayout.setHorizontalSpacing(4)
        self.flowLayout.setVerticalSpacing(4)
        self.flowLayout.addWidget(self.lineEdit)

    def _bind(self) -> None:
        self.lineEdit.submitted.connect(self._addToken)

    def tokens(self) -> list[str]:
        return list(self._tokens)

    def setTokens(self, tokens: list[str]) -> None:
        self._clearAllTokenWidgets()
        self._tokens.clear()
        for t in tokens:
            self._insertTokenWidget(t)
        self.tokensChanged.emit(self.tokens())

    def setMaxTokenCount(self, count: int) -> None:
        self._maxTokenCount = count
        self._updateInputVisibility()

    def maxTokenCount(self) -> int:
        return self._maxTokenCount

    def setPlaceholderText(self, text: str) -> None:
        self.lineEdit.setPlaceholderText(text)

    def _addToken(self, text: str) -> None:
        if self._maxTokenCount > 0 and len(self._tokens) >= self._maxTokenCount:
            return
        if text in self._tokens:
            return
        self._insertTokenWidget(text)
        self.tokensChanged.emit(self.tokens())

    def _insertTokenWidget(self, text: str) -> None:
        self._tokens.append(text)
        widget = _TokenWidget(text, self)
        widget.closeClicked.connect(self._removeTokenWidget)
        self._tokenWidgets.append(widget)

        index = self.flowLayout.count() - 1
        self.flowLayout.insertWidget(index, widget)
        widget.show()
        self._updateTokenWidths()
        self._updateInputVisibility()
        self._invalidateLayout()

    def _removeTokenWidget(self, widget: _TokenWidget) -> None:
        idx = self._tokenWidgets.index(widget)
        self._tokens.pop(idx)
        self._tokenWidgets.pop(idx)
        self.flowLayout.removeWidget(widget)
        widget.hide()
        widget.deleteLater()
        self._updateInputVisibility()
        self._invalidateLayout()
        self.tokensChanged.emit(self.tokens())

    def _clearAllTokenWidgets(self) -> None:
        for w in self._tokenWidgets:
            self.flowLayout.removeWidget(w)
            w.hide()
            w.deleteLater()
        self._tokenWidgets.clear()
        self._invalidateLayout()

    def _invalidateLayout(self) -> None:
        self.flowLayout.invalidate()
        self.flowLayout.setGeometry(self.flowLayout.geometry())
        self.updateGeometry()
        self.update()

    def _updateInputVisibility(self) -> None:
        if self._maxTokenCount > 0 and len(self._tokens) >= self._maxTokenCount:
            self.lineEdit.hide()
        else:
            self.lineEdit.show()

    def _updateTokenWidths(self) -> None:
        maxWidth = self.width() - 12
        if maxWidth <= 0:
            return
        for w in self._tokenWidgets:
            w.elide(maxWidth)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._updateTokenWidths()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.lineEdit.setFocus()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.lineEdit:
            if event.type() == event.Type.KeyPress:
                if event.key() == Qt.Key.Key_Backspace and not self.lineEdit.text():
                    if self._tokenWidgets:
                        self._removeTokenWidget(self._tokenWidgets[-1])
                    return True
            elif event.type() == event.Type.FocusIn:
                self._hasFocus = True
                self.update()
            elif event.type() == event.Type.FocusOut:
                self._hasFocus = False
                self.update()
                text = self.lineEdit.text().strip()
                if text:
                    self._addToken(text)
                    self.lineEdit.clear()
        return super().eventFilter(obj, event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if isDarkTheme():
            bgColor = QColor(255, 255, 255, 13)
            borderColor = QColor(255, 255, 255, 18)
        else:
            bgColor = QColor(255, 255, 255, 170)
            borderColor = QColor(0, 0, 0, 22)

        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 4, 4)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bgColor)
        painter.drawPath(path)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(borderColor)
        painter.drawPath(path)

        if self._hasFocus:
            accentColor = autoFallbackThemeColor(QColor(), QColor())
            barPath = QPainterPath()
            barPath.addRoundedRect(QRectF(0, h - 10, w, 10), 5, 5)
            rectPath = QPainterPath()
            rectPath.addRect(0, h - 10, w, 8)
            barPath = barPath.subtracted(rectPath)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accentColor)
            painter.drawPath(barPath)
