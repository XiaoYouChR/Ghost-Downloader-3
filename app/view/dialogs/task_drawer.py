from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QEasingCurve, QFileInfo, QParallelAnimationGroup, QPoint, QPointF, QPropertyAnimation, Qt, QTimer,
)
from PySide6.QtGui import QColor, QFont, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFileIconProvider, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QHeaderView, QSizePolicy, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, FluentIcon, ImageLabel, InfoBar, InfoBarIcon, InfoBarPosition, LineEdit, ProgressBar, ScrollArea,
    SimpleCardWidget, StrongBodyLabel, SubtitleLabel, TableWidget, ToolTipFilter,
    TransparentToolButton, isDarkTheme, setFont,
)
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase
from qfluentwidgets.components.widgets.menu import TextEditMenu

from app.config.cfg import cfg
from app.format import toReadableSize, toReadableTime
from app.i18n import toLocalizedError
from app.models.task import TaskStatus
from app.platform.desktop import revealInFolder
from app.view.components.category_settings import toCategoryName

if TYPE_CHECKING:
    from app.models.task import Task

DRAWER_WIDTH = 592
SLIDE_DURATION = 300
CAPTION_WIDTH = 88
MATCH_COLORS = ("#0F7B0F", "#6CCB5F")
ROW_BUTTON_SIZE = 28


def toBezierCurve(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1, 1))
    return curve


def toTimeText(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def matchChecksum(task: Task, expected: str) -> str | None:
    expected = expected.strip().lower()
    return next((algorithm for algorithm, value in task.checksums.items() if value == expected), None)


def toCaptionStyle(label: CaptionLabel) -> None:
    label.setFixedWidth(CAPTION_WIDTH)
    label.setTextColor(QColor(96, 96, 96), QColor(206, 206, 206))


class SelectableText(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background: transparent; color: {'white' if isDarkTheme() else 'black'}")
        self.document().setDocumentMargin(0)
        self.document().documentLayout().documentSizeChanged.connect(
            lambda size: self.setFixedHeight(ceil(size.height())))
        setFont(self, 14)

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, text: str) -> None:
        if text != self.toPlainText():
            self.setPlainText(text)

    def contextMenuEvent(self, e) -> None:
        TextEditMenu(self).exec(e.globalPos())

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)
        if e.reason() in (Qt.FocusReason.ActiveWindowFocusReason, Qt.FocusReason.PopupFocusReason):
            return
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)


class InfoRow(QWidget):
    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.captionLabel = CaptionLabel(caption, self)
        self.valueText = SelectableText(self)
        self.buttonLayout = QHBoxLayout()
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        toCaptionStyle(self.captionLabel)

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.captionLabel, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.valueText, 1)
        layout.addLayout(self.buttonLayout)
        self.buttonLayout.setSpacing(2)

    def setValue(self, text: str) -> None:
        self.valueText.setText(text)

    def addButton(self, icon, tooltip: str, onClick) -> None:
        button = TransparentToolButton(icon, self)
        button.setFixedSize(ROW_BUTTON_SIZE, ROW_BUTTON_SIZE)
        button.setToolTip(tooltip)
        button.installEventFilter(ToolTipFilter(button))
        button.clicked.connect(onClick)
        self.buttonLayout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)

    def addCopyButton(self) -> None:
        self.addButton(FluentIcon.COPY, self.tr("复制"),
                       lambda: QApplication.clipboard().setText(self.valueText.text()))


class DetailCard(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.titleLabel = StrongBodyLabel(title, self)
        self.card = SimpleCardWidget(self)
        self.bodyLayout = QVBoxLayout(self.card)
        self._initDetailLayout()

    def _initDetailLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.titleLabel)
        layout.addWidget(self.card)
        self.bodyLayout.setContentsMargins(16, 12, 16, 12)
        self.bodyLayout.setSpacing(10)

    def refresh(self) -> None:
        pass


class HeaderCard(QWidget):
    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self._task = task
        self.iconLabel = ImageLabel(self)
        self.nameText = SelectableText(self)
        self.statusLabel = CaptionLabel(self)
        self.progressBar = ProgressBar(self)
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        setFont(self.nameText, 20, QFont.Weight.DemiBold)

    def _initLayout(self) -> None:
        textLayout = QVBoxLayout()
        textLayout.setSpacing(4)
        textLayout.addWidget(self.nameText)
        textLayout.addWidget(self.statusLabel)
        textLayout.addWidget(self.progressBar)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(textLayout, 1)

    def refresh(self) -> None:
        task = self._task
        self.nameText.setText(task.name)
        self.iconLabel.setPixmap(QFileIconProvider().icon(QFileInfo(task.outputPath)).pixmap(48, 48))
        self.iconLabel.setFixedSize(48, 48)
        progress, speed, received = task.currentSnapshot()
        self.progressBar.setVisible(task.status != TaskStatus.COMPLETED and task.fileSize > 0)
        self.progressBar.setValue(int(progress))
        self.progressBar.setError(task.status == TaskStatus.FAILED)
        self.statusLabel.setText(self._toStatusText(speed, received))

    def _toStatusText(self, speed: int, received: int) -> str:
        task = self._task
        if task.status == TaskStatus.RUNNING:
            parts = [f"{toReadableSize(speed)}/s"]
            if task.fileSize > 0:
                parts.append(f"{toReadableSize(received)} / {toReadableSize(task.fileSize)}")
                if speed > 0:
                    parts.append(toReadableTime(int((task.fileSize - received) / speed)))
            return " · ".join(parts)
        if task.status == TaskStatus.COMPLETED:
            return self.tr("做种中") if task.isSeeding else self.tr("已完成")
        if task.status == TaskStatus.FAILED:
            return self.tr("失败")
        if task.status == TaskStatus.PAUSED:
            return self.tr("已暂停")
        return self.tr("等待中")


class InfoCard(DetailCard):
    def __init__(self, task: Task, categoryService, parent=None):
        super().__init__(self.tr("信息"), parent)
        self._task = task
        self._categoryService = categoryService
        self.urlRow = InfoRow(self.tr("下载链接"), self.card)
        self.pathRow = InfoRow(self.tr("保存位置"), self.card)
        self.sizeRow = InfoRow(self.tr("大小"), self.card)
        self.categoryRow = InfoRow(self.tr("分类"), self.card)
        self.createdRow = InfoRow(self.tr("创建时间"), self.card)
        self.completedRow = InfoRow(self.tr("完成时间"), self.card)
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.urlRow.addCopyButton()
        self.pathRow.addCopyButton()
        self.pathRow.addButton(FluentIcon.FOLDER, self.tr("在文件夹中显示"),
                               lambda: revealInFolder(self._task.outputPath))

    def _initLayout(self) -> None:
        for row in (self.urlRow, self.pathRow, self.sizeRow, self.categoryRow, self.createdRow, self.completedRow):
            self.bodyLayout.addWidget(row)

    def refresh(self) -> None:
        task = self._task
        self.urlRow.setValue(task.url)
        self.pathRow.setValue(task.outputPath)
        self.sizeRow.setVisible(task.fileSize > 0)
        self.sizeRow.setValue(toReadableSize(task.fileSize))
        category = self._categoryService.categoryById(task.category) if task.category else None
        self.categoryRow.setVisible(cfg.isCategoryEnabled.value)
        self.categoryRow.setValue(toCategoryName(category) if category else self.tr("未分类"))
        self.createdRow.setValue(toTimeText(task.createdAt))
        self.completedRow.setVisible(bool(task.completedAt))
        self.completedRow.setValue(toTimeText(task.completedAt) if task.completedAt else "")


class ChecksumCard(DetailCard):
    def __init__(self, task: Task, parent=None):
        super().__init__(self.tr("校验值"), parent)
        self._task = task
        self._shownChecksums: dict[str, str] = {}
        self.rowsLayout = QVBoxLayout()
        self.compareLabel = CaptionLabel(self.tr("比对"), self.card)
        self.expectedEdit = LineEdit(self.card)
        self.pasteButton = TransparentToolButton(FluentIcon.PASTE, self.card)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        toCaptionStyle(self.compareLabel)
        self.expectedEdit.setPlaceholderText(self.tr("粘贴期望值"))
        self.expectedEdit.setClearButtonEnabled(True)
        self.expectedEdit.installEventFilter(ToolTipFilter(self.expectedEdit))
        self.pasteButton.setFixedSize(ROW_BUTTON_SIZE, ROW_BUTTON_SIZE)
        self.pasteButton.setToolTip(self.tr("粘贴"))
        self.pasteButton.installEventFilter(ToolTipFilter(self.pasteButton))

    def _initLayout(self) -> None:
        compareLayout = QHBoxLayout()
        compareLayout.setSpacing(12)
        compareLayout.addWidget(self.compareLabel)
        compareLayout.addWidget(self.expectedEdit, 1)
        compareLayout.addWidget(self.pasteButton)

        self.rowsLayout.setSpacing(10)
        self.bodyLayout.addLayout(self.rowsLayout)
        self.bodyLayout.addLayout(compareLayout)

    def _bind(self) -> None:
        self.expectedEdit.textChanged.connect(self._refreshMatch)
        self.pasteButton.clicked.connect(self._onPasteClicked)

    def refresh(self) -> None:
        task = self._task
        self.setVisible(bool(task.checksums) and not (task.files and len(task.files) > 1))
        if task.checksums == self._shownChecksums:
            return
        self._shownChecksums = dict(task.checksums)
        while self.rowsLayout.count():
            self.rowsLayout.takeAt(0).widget().deleteLater()
        for algorithm, value in sorted(task.checksums.items()):
            row = InfoRow(algorithm.upper(), self.card)
            row.setValue(value)
            row.addCopyButton()
            self.rowsLayout.addWidget(row)
        self._refreshMatch()

    def _refreshMatch(self) -> None:
        expected = self.expectedEdit.text()
        algorithm = matchChecksum(self._task, expected)
        self.expectedEdit.setError(bool(expected.strip()) and algorithm is None)
        if algorithm:
            self.expectedEdit.setCustomFocusedBorderColor(*MATCH_COLORS)
            self.expectedEdit.setToolTip(self.tr("与 {0} 一致").format(algorithm.upper()))
        else:
            self.expectedEdit.setCustomFocusedBorderColor(QColor(), QColor())
            self.expectedEdit.setToolTip(self.tr("与已计算的校验值都不一致") if expected.strip() else "")

    def _onPasteClicked(self) -> None:
        self.expectedEdit.setText(QApplication.clipboard().text())
        self.expectedEdit.setFocus()


class ErrorBar(QWidget):
    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self._task = task
        self._shownText = ""
        self.bar: InfoBar | None = None
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)

    def refresh(self) -> None:
        error = self._task.lastError if self._task.status == TaskStatus.FAILED else None
        text = toLocalizedError(error) if error is not None else ""
        self.setVisible(bool(text))
        if text == self._shownText:
            return
        self._shownText = text
        if self.bar is not None:
            self.bar.deleteLater()
            self.bar = None
        if not text:
            return
        self.bar = InfoBar(InfoBarIcon.ERROR, self.tr("下载失败"), text, Qt.Orientation.Horizontal,
                           isClosable=False, duration=-1, position=InfoBarPosition.NONE, parent=self)
        self.bar.setGraphicsEffect(None)
        self.bar.setFixedWidth(self.width())
        self.bar.textLayout.setStretchFactor(self.bar.titleLabel, 0)
        copyButton = TransparentToolButton(FluentIcon.COPY, self.bar)
        copyButton.setToolTip(self.tr("复制"))
        copyButton.installEventFilter(ToolTipFilter(copyButton))
        copyButton.clicked.connect(lambda: QApplication.clipboard().setText(text))
        self.bar.addWidget(copyButton)
        self.vBoxLayout.addWidget(self.bar)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.bar is not None:
            self.bar.setFixedWidth(self.width())


class DetailTable(TableWidget):
    def __init__(self, headers: list[str], stretchColumns: tuple[int, ...] = (0,),
                 elideMode: Qt.TextElideMode = Qt.TextElideMode.ElideRight, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().hide()
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        for column in stretchColumns:
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.setTextElideMode(elideMode)
        self.setWordWrap(False)

    def setRows(self, rows: list[tuple[str, ...]], toolTips: list[str] | None = None) -> None:
        self.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, text in enumerate(values):
                item = self.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.setItem(row, column, item)
                item.setText(text)
                item.setToolTip(toolTips[row] if toolTips else text)
        self.setFixedHeight(self.horizontalHeader().height() + self.verticalHeader().length() + 2 * self.frameWidth())


class FileListCard(DetailCard):
    def __init__(self, task: Task, parent=None):
        super().__init__(self.tr("文件"), parent)
        self._task = task
        self._lastStatus: TaskStatus | None = None
        self.table = DetailTable([self.tr("文件"), self.tr("大小"), self.tr("状态")], parent=self.card)
        self.bodyLayout.setContentsMargins(0, 0, 0, 0)
        self.bodyLayout.addWidget(self.table)

    def refresh(self) -> None:
        task = self._task
        files = task.files or []
        self.setVisible(len(files) > 1)
        if len(files) <= 1 or (task.status == self._lastStatus and task.status != TaskStatus.RUNNING):
            return
        self._lastStatus = task.status
        self.table.setRows([
            (task.toDisplayPath(file), toReadableSize(file.size), self._toFileStatusText(file)) for file in files
        ])

    def _toFileStatusText(self, file) -> str:
        if not file.selected:
            return self.tr("未选择")
        if file.completed:
            return self.tr("已完成")
        return f"{file.downloadedBytes * 100 // file.size}%" if file.size > 0 else "--"


class TaskDrawer(MaskDialogBase):
    def __init__(self, task: Task, taskService, featureService, categoryService, parent):
        super().__init__(parent)
        self._task = task
        self._taskService = taskService
        self.titleLabel = SubtitleLabel(self.tr("任务详情"), self.widget)
        self.closeButton = TransparentToolButton(FluentIcon.CLOSE, self.widget)
        self.scrollArea = ScrollArea(self.widget)
        self.scrollWidget = QWidget()
        self.cards: list[QWidget] = [
            HeaderCard(task, self.scrollWidget),
            ErrorBar(task, self.scrollWidget),
            InfoCard(task, categoryService, self.scrollWidget),
            ChecksumCard(task, self.scrollWidget),
            FileListCard(task, self.scrollWidget),
            *featureService.detailCards(task, self.scrollWidget),
        ]
        self.refreshTimer = QTimer(self)
        self.slideAnimation = QPropertyAnimation(self.widget, b"pos", self)
        self.maskEffect = QGraphicsOpacityEffect(self.windowMask)
        self.closeAnimation = QParallelAnimationGroup(self)
        self.slideOutAnimation = QPropertyAnimation(self.widget, b"pos", self.closeAnimation)
        self.maskFadeAnimation = QPropertyAnimation(self.maskEffect, b"opacity", self.closeAnimation)
        self._resultCode = 0
        self._initWidget()
        self._initLayout()
        self._bind()
        self._refresh()

    def _initWidget(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setClosableOnMaskClicked(True)
        self.setMaskColor(QColor(0, 0, 0, 128) if isDarkTheme() else QColor(0, 0, 0, 102))
        self.setShadowEffect(64, (0, 0), QColor(0, 0, 0, 61))
        self._hBoxLayout.removeWidget(self.widget)
        self.widget.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        background = "rgb(41, 41, 41)" if isDarkTheme() else "rgb(255, 255, 255)"
        self.widget.setStyleSheet(f"#centerWidget {{ background-color: {background}; border: none; }}")
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollArea.enableTransparentBackground()
        self.scrollWidget.setStyleSheet("background: transparent")
        self.refreshTimer.setInterval(1000)
        self.slideAnimation.setDuration(SLIDE_DURATION)
        self.slideAnimation.setEasingCurve(toBezierCurve(0, 0, 0, 1))
        self.maskEffect.setOpacity(1)
        self.windowMask.setGraphicsEffect(self.maskEffect)
        self.slideOutAnimation.setDuration(SLIDE_DURATION)
        self.slideOutAnimation.setEasingCurve(toBezierCurve(0.8, 0, 0.78, 1))
        self.maskFadeAnimation.setDuration(SLIDE_DURATION)
        self.maskFadeAnimation.setEndValue(0)

    def _initLayout(self) -> None:
        titleLayout = QHBoxLayout()
        titleLayout.setContentsMargins(24, 24, 24, 8)
        titleLayout.addWidget(self.titleLabel)
        titleLayout.addStretch()
        titleLayout.addWidget(self.closeButton)

        scrollLayout = QVBoxLayout(self.scrollWidget)
        scrollLayout.setContentsMargins(24, 8, 24, 24)
        scrollLayout.setSpacing(20)
        for card in self.cards:
            scrollLayout.addWidget(card)
        scrollLayout.addStretch()

        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(titleLayout)
        layout.addWidget(self.scrollArea, 1)

    def _bind(self) -> None:
        self.closeButton.clicked.connect(self.reject)
        self.refreshTimer.timeout.connect(self._refresh)
        self.closeAnimation.finished.connect(lambda: QDialog.done(self, self._resultCode))
        self._taskService.taskRemoved.connect(self._onTaskRemoved, owner=self)

    def _refresh(self) -> None:
        for card in self.cards:
            card.refresh()

    def _onTaskRemoved(self, taskId: str) -> None:
        if taskId == self._task.taskId:
            self.reject()

    def _toDrawerWidth(self) -> int:
        return min(DRAWER_WIDTH, self.width())

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.refreshTimer.start()
        width = self._toDrawerWidth()
        self.widget.setGeometry(self.width(), 0, width, self.height())
        self.slideAnimation.setStartValue(QPoint(self.width(), 0))
        self.slideAnimation.setEndValue(QPoint(self.width() - width, 0))
        self.slideAnimation.start()

    def done(self, code: int) -> None:
        if self.closeAnimation.state() == QParallelAnimationGroup.State.Running:
            return
        self._resultCode = code
        self.refreshTimer.stop()
        self.slideAnimation.stop()
        self.slideOutAnimation.setStartValue(self.widget.pos())
        self.slideOutAnimation.setEndValue(QPoint(self.width(), 0))
        self.maskFadeAnimation.setStartValue(self.maskEffect.opacity())
        self.closeAnimation.start()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.closeAnimation.state() == QParallelAnimationGroup.State.Running:
            return
        width = self._toDrawerWidth()
        self.slideAnimation.stop()
        self.widget.setGeometry(self.width() - width, 0, width, self.height())
