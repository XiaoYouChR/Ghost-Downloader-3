from __future__ import annotations

from typing import Final

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import (
    EditableComboBox, FluentIcon, PlainTextEdit, ToolTipFilter,
    TransparentToolButton,
)


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
