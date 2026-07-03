from typing import Final

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QKeyEvent, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget,
)
from qfluentwidgets import (
    EditableComboBox, FlowLayout, FluentIcon, PlainTextEdit,
    ToolTipFilter, TransparentToolButton, isDarkTheme,
)
from qfluentwidgets.common.color import autoFallbackThemeColor
from qfluentwidgets.common.font import setFont


class AutoSizingEdit(PlainTextEdit):
    def __init__(self, parent=None, *, minimumVisibleLines: int = 5,
                 maximumVisibleLines: int | None = None):
        super().__init__(parent)
        self._minimumVisibleLines = minimumVisibleLines
        self._maximumVisibleLines = maximumVisibleLines
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.document().blockCountChanged.connect(self.updateGeometry)

    def _sizeForLines(self, count: int) -> QSize:
        margins = self.contentsMargins()
        viewportMargins = self.viewportMargins()
        padding = (
            margins.top() + margins.bottom()
            + viewportMargins.top() + viewportMargins.bottom()
            + self.frameWidth() * 2
            + round(self.document().documentMargin() * 2)
        )
        return QSize(super().sizeHint().width(),
                      padding + self.fontMetrics().lineSpacing() * count)

    def minimumSizeHint(self) -> QSize:
        return self._sizeForLines(min(self._minimumVisibleLines, self.document().blockCount()))

    def sizeHint(self) -> QSize:
        count = self.document().blockCount()
        if self._maximumVisibleLines is not None:
            count = min(count, self._maximumVisibleLines)
        return self._sizeForLines(count).expandedTo(self.minimumSizeHint())


COMBO_PADDING: Final[int] = 60


class AutoSizingComboBox(EditableComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.currentTextChanged.connect(self.updateGeometry)

    def sizeHint(self) -> QSize:
        textWidth = self.fontMetrics().horizontalAdvance(self.currentText())
        return QSize(textWidth + COMBO_PADDING, super().sizeHint().height())


class FolderPicker(QWidget):
    pathChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.comboBox = AutoSizingComboBox(self)
        self.browseButton = TransparentToolButton(FluentIcon.FOLDER, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.comboBox.setMinimumWidth(200)
        self.browseButton.setFixedSize(28, 28)
        self.browseButton.setToolTip(self.tr("浏览文件夹"))
        self.browseButton.installEventFilter(ToolTipFilter(self.browseButton))

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.comboBox, 1)
        layout.addWidget(self.browseButton)

    def _bind(self) -> None:
        self.browseButton.clicked.connect(self._onBrowseClicked)
        self.comboBox.activated.connect(self._commit)
        self.comboBox.editingFinished.connect(self._commit)

    def path(self) -> str:
        return self.comboBox.currentText().strip()

    def setPath(self, path: str) -> None:
        self.comboBox.setText(path)

    def saveHistory(self, path: str) -> None:
        from app.config.cfg import cfg
        history = list(cfg.memoryDownloadFolders.value)
        if path in history:
            history.remove(path)
        history.insert(0, path)
        cfg.set(cfg.memoryDownloadFolders, history[:20])
        self.refreshHistory()

    def refreshHistory(self) -> None:
        from app.config.cfg import cfg
        current = self.comboBox.currentText()
        self.comboBox.clear()
        for folder in cfg.memoryDownloadFolders.value:
            if folder:
                self.comboBox.addItem(folder)
        self.comboBox.setText(current)

    def _commit(self) -> None:
        path = self.path()
        if path:
            self.pathChanged.emit(path)

    def _onBrowseClicked(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(
            self.window(), self.tr("选择文件夹"), self.path()
        )
        if folder:
            self.comboBox.setCurrentText(folder)
            self.pathChanged.emit(folder)


class TokenWidget(QWidget):
    closeClicked = Signal(QWidget)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text

        self.label = QLabel(self)
        self.closeButton = TransparentToolButton(FluentIcon.CLOSE, self)

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
        self.label.setText(fm.elidedText(self._text, Qt.TextElideMode.ElideRight, available))
        self.setMaximumWidth(maxWidth)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 20) if isDarkTheme() else QColor(0, 0, 0, 12))
        painter.drawRoundedRect(self.rect(), 4, 4)


class TokenInput(QLineEdit):
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
        self._tokenWidgets: list[TokenWidget] = []
        self._maxTokenCount = maxTokenCount
        self._hasFocus = False

        self.flowLayout = FlowLayout(self, needAni=False, isTight=True)
        self.lineEdit = TokenInput(self)

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
        self._clearAll()
        for t in tokens:
            self._insertToken(t)
        self.tokensChanged.emit(self.tokens())

    def setMaxTokenCount(self, count: int) -> None:
        self._maxTokenCount = count
        self._refreshInputVisibility()

    def setPlaceholderText(self, text: str) -> None:
        self.lineEdit.setPlaceholderText(text)

    def _addToken(self, text: str) -> None:
        if self._maxTokenCount > 0 and len(self._tokens) >= self._maxTokenCount:
            return
        if text in self._tokens:
            return
        self._insertToken(text)
        self.tokensChanged.emit(self.tokens())

    def _insertToken(self, text: str) -> None:
        self._tokens.append(text)
        widget = TokenWidget(text, self)
        widget.closeClicked.connect(self._removeToken)
        self._tokenWidgets.append(widget)
        self.flowLayout.insertWidget(self.flowLayout.count() - 1, widget)
        widget.show()
        self._refreshTokenWidths()
        self._refreshInputVisibility()
        self._invalidateLayout()

    def _removeToken(self, widget: TokenWidget) -> None:
        idx = self._tokenWidgets.index(widget)
        self._tokens.pop(idx)
        self._tokenWidgets.pop(idx)
        self.flowLayout.removeWidget(widget)
        widget.hide()
        widget.deleteLater()
        self._refreshInputVisibility()
        self._invalidateLayout()
        self.tokensChanged.emit(self.tokens())

    def _clearAll(self) -> None:
        for w in self._tokenWidgets:
            self.flowLayout.removeWidget(w)
            w.hide()
            w.deleteLater()
        self._tokenWidgets.clear()
        self._tokens.clear()
        self._invalidateLayout()

    def _invalidateLayout(self) -> None:
        self.flowLayout.invalidate()
        self.flowLayout.setGeometry(self.flowLayout.geometry())
        self.updateGeometry()
        self.update()

    def _refreshInputVisibility(self) -> None:
        self.lineEdit.setVisible(
            self._maxTokenCount <= 0 or len(self._tokens) < self._maxTokenCount
        )

    def _refreshTokenWidths(self) -> None:
        maxWidth = self.width() - 12
        if maxWidth > 0:
            for w in self._tokenWidgets:
                w.elide(maxWidth)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refreshTokenWidths()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.lineEdit.setFocus()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.lineEdit:
            if event.type() == event.Type.KeyPress:
                if event.key() == Qt.Key.Key_Backspace and not self.lineEdit.text():
                    if self._tokenWidgets:
                        self._removeToken(self._tokenWidgets[-1])
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

        bgColor = QColor(255, 255, 255, 13 if isDarkTheme() else 170)
        borderColor = QColor(255, 255, 255, 18) if isDarkTheme() else QColor(0, 0, 0, 22)

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
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accentColor)
            painter.drawPath(barPath.subtracted(rectPath))


def headersToText(headers: dict[str, str]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in headers.items())


def headersFromText(text: str) -> dict[str, str]:
    headers = {}
    for line in text.strip().splitlines():
        name, _, value = line.partition(":")
        name = name.strip()
        value = value.strip()
        if name and value:
            headers[name] = value
    return headers
