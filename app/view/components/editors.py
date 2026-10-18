from __future__ import annotations

from pathlib import Path
from typing import Callable, Final

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import (
    Action, BodyLabel, CaptionLabel, FluentIcon, LineEdit, PlainTextEdit,
    RoundMenu, ToolTipFilter, TransparentToolButton,
)

from app.config.cfg import cfg


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


RECENT_FOLDER_LIMIT: Final[int] = 20
LINE_EDIT_PADDING: Final[int] = 60
MENU_ROW_HEIGHT: Final[int] = 36


def addRecentFolder(path: str) -> None:
    others = [folder for folder in cfg.recentFolders.value if Path(folder) != Path(path)]
    cfg.set(cfg.recentFolders, [path, *others][:RECENT_FOLDER_LIMIT])


class AutoSizingLineEdit(LineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.textChanged.connect(self.updateGeometry)

    def sizeHint(self) -> QSize:
        textWidth = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(textWidth + LINE_EDIT_PADDING, super().sizeHint().height())


class FolderPicker(QWidget):
    pathChanged = Signal(str)

    def __init__(self, pinnedPath: Callable[[], str], pinnedLabel: str, parent=None):
        super().__init__(parent)
        self._pinnedPath = pinnedPath
        self._pinnedLabel = pinnedLabel
        self.lineEdit = AutoSizingLineEdit(self)
        self.menuAction = Action(FluentIcon.ARROW_DOWN, self.tr("常用文件夹"), self)
        self.browseButton = TransparentToolButton(FluentIcon.FOLDER, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.lineEdit.setMinimumWidth(200)
        self.lineEdit.addAction(self.menuAction)
        self.browseButton.setFixedSize(28, 28)
        self.browseButton.setToolTip(self.tr("浏览文件夹"))
        self.browseButton.installEventFilter(ToolTipFilter(self.browseButton))

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.lineEdit, 1)
        layout.addWidget(self.browseButton)

    def _bind(self) -> None:
        self.browseButton.clicked.connect(self._onBrowseClicked)
        self.menuAction.triggered.connect(lambda: self._openMenu())
        self.lineEdit.editingFinished.connect(self._onEditingFinished)

    def path(self) -> str:
        return self.lineEdit.text().strip()

    def setPath(self, path: str) -> None:
        self.lineEdit.setText(path)
        self.lineEdit.setModified(False)

    def _onPathPicked(self, path: str) -> None:
        self.setPath(path)
        self.pathChanged.emit(path)

    def _onEditingFinished(self) -> None:
        if not self.lineEdit.isModified() or not self.path():
            return
        self._onPathPicked(self.path())

    def _onBrowseClicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(self.window(), self.tr("选择文件夹"), self.path())
        if folder:
            self._onPathPicked(folder)

    def _openMenu(self, isAnimated: bool = True) -> None:
        menu = RoundMenu(parent=self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.setItemHeight(MENU_ROW_HEIGHT)
        width = self.lineEdit.width()
        pinned = self._pinnedPath()

        caption = CaptionLabel(self._pinnedLabel)
        caption.setTextColor(QColor(96, 96, 96), QColor(206, 206, 206))
        menu.addWidget(self._buildRow(pinned, caption, width),
                       onClick=lambda checked=False: self._onPathPicked(pinned))

        for folder in cfg.recentFolders.value:
            if Path(folder) == Path(pinned):
                continue
            deleteButton = TransparentToolButton(FluentIcon.CLOSE)
            deleteButton.setFixedSize(24, 24)
            deleteButton.setIconSize(QSize(10, 10))
            deleteButton.setToolTip(self.tr("从常用文件夹中移除"))
            deleteButton.installEventFilter(ToolTipFilter(deleteButton))
            deleteButton.clicked.connect(
                lambda checked=False, f=folder: self._onRecentFolderDeleted(menu, f)
            )
            menu.addWidget(self._buildRow(folder, deleteButton, width),
                           onClick=lambda checked=False, f=folder: self._onPathPicked(f))

        menu.exec(self.lineEdit.mapToGlobal(QPoint(0, self.lineEdit.height())), ani=isAnimated)

    def _buildRow(self, folder: str, trailing: QWidget, width: int) -> QWidget:
        row = QWidget()
        row.resize(width, MENU_ROW_HEIGHT)
        label = BodyLabel(row)
        label.setText(label.fontMetrics().elidedText(folder, Qt.TextElideMode.ElideMiddle, width - 90))
        label.setToolTip(folder)
        label.installEventFilter(ToolTipFilter(label))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.addWidget(label, 1)
        layout.addWidget(trailing)
        return row

    def _onRecentFolderDeleted(self, menu: RoundMenu, folder: str) -> None:
        cfg.set(cfg.recentFolders, [item for item in cfg.recentFolders.value if item != folder])
        menu.close()
        self._openMenu(isAnimated=False)
