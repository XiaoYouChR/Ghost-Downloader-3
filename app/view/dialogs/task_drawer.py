from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QEasingCurve, QFileInfo, QPoint, QPointF, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QTextLayout, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileIconProvider, QHBoxLayout, QHeaderView,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, FluentIcon, ImageLabel, LineEdit, ProgressBar, ScrollArea,
    SimpleCardWidget, StrongBodyLabel, SubtitleLabel, TableWidget, ToolTipFilter,
    TransparentToolButton, isDarkTheme, setFont,
)
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

from app.config.cfg import cfg
from app.format import toReadableSize, toReadableTime
from app.i18n import toLocalizedError
from app.models.task import TaskStatus
from app.platform.desktop import revealInFolder
from app.view.components.category_settings import toCategoryName

if TYPE_CHECKING:
    from app.models.task import Task

DRAWER_MAX_WIDTH = 640
DRAWER_WIDTH_RATIO = 0.6
SLIDE_DURATION = 250
CAPTION_WIDTH = 88
MATCH_COLORS = ("#0F7B0F", "#6CCB5F")
ROW_BUTTON_SIZE = 28


def toTimeText(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def matchChecksum(task: Task, expected: str) -> str | None:
    expected = expected.strip().lower()
    return next((algorithm for algorithm, value in task.checksums.items() if value == expected), None)


def toCaptionStyle(label: CaptionLabel) -> None:
    label.setFixedWidth(CAPTION_WIDTH)
    label.setTextColor(QColor(96, 96, 96), QColor(206, 206, 206))


class WrapLabel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        setFont(self, 14)
        sizePolicy = self.sizePolicy()
        sizePolicy.setHeightForWidth(True)
        self.setSizePolicy(sizePolicy)

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        self.updateGeometry()
        self.update()

    def _buildLayout(self, width: int) -> QTextLayout:
        layout = QTextLayout(self._text, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        y = 0.0
        while (line := layout.createLine()).isValid():
            line.setLineWidth(width)
            line.setPosition(QPointF(0, y))
            y += line.height()
        layout.endLayout()
        return layout

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return int(self._buildLayout(max(width, 1)).boundingRect().height()) + 1

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self._text), self.heightForWidth(self.width()))

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self.fontMetrics().height())

    def paintEvent(self, e) -> None:
        painter = QPainter(self)
        painter.setPen(QColor(255, 255, 255) if isDarkTheme() else QColor(0, 0, 0))
        self._buildLayout(self.width()).draw(painter, QPointF(0, 0))


class InfoRow(QWidget):
    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.captionLabel = CaptionLabel(caption, self)
        self.valueLabel = WrapLabel(self)
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
        layout.addWidget(self.valueLabel, 1)
        layout.addLayout(self.buttonLayout)
        self.buttonLayout.setSpacing(2)

    def setValue(self, text: str) -> None:
        self.valueLabel.setText(text)

    def addButton(self, icon, tooltip: str, onClick) -> None:
        button = TransparentToolButton(icon, self)
        button.setFixedSize(ROW_BUTTON_SIZE, ROW_BUTTON_SIZE)
        button.setToolTip(tooltip)
        button.installEventFilter(ToolTipFilter(button))
        button.clicked.connect(onClick)
        self.buttonLayout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)

    def addCopyButton(self) -> None:
        self.addButton(FluentIcon.COPY, self.tr("复制"),
                       lambda: QApplication.clipboard().setText(self.valueLabel.text()))


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
        self.nameLabel = SubtitleLabel(task.name, self)
        self.statusLabel = CaptionLabel(self)
        self.progressBar = ProgressBar(self)
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.nameLabel.setWordWrap(True)
        self.nameLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def _initLayout(self) -> None:
        textLayout = QVBoxLayout()
        textLayout.setSpacing(4)
        textLayout.addWidget(self.nameLabel)
        textLayout.addWidget(self.statusLabel)
        textLayout.addWidget(self.progressBar)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(textLayout, 1)

    def refresh(self) -> None:
        task = self._task
        self.nameLabel.setText(task.name)
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


class ErrorCard(DetailCard):
    def __init__(self, task: Task, parent=None):
        super().__init__(self.tr("错误"), parent)
        self._task = task
        self.errorRow = InfoRow(self.tr("原因"), self.card)
        self.errorRow.addCopyButton()
        self.bodyLayout.addWidget(self.errorRow)

    def refresh(self) -> None:
        error = self._task.lastError if self._task.status == TaskStatus.FAILED else None
        self.setVisible(error is not None)
        if error is not None:
            self.errorRow.setValue(toLocalizedError(error))


class FileListCard(DetailCard):
    def __init__(self, task: Task, parent=None):
        super().__init__(self.tr("文件"), parent)
        self._task = task
        self._lastStatus: TaskStatus | None = None
        self.table = TableWidget(self.card)
        self._initWidget()
        self.bodyLayout.setContentsMargins(0, 0, 0, 0)
        self.bodyLayout.addWidget(self.table)

    def _initWidget(self) -> None:
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([self.tr("文件"), self.tr("大小"), self.tr("状态")])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    def refresh(self) -> None:
        task = self._task
        files = task.files or []
        self.setVisible(len(files) > 1)
        if len(files) <= 1 or (task.status == self._lastStatus and task.status != TaskStatus.RUNNING):
            return
        self._lastStatus = task.status
        if self.table.rowCount() != len(files):
            self.table.setRowCount(len(files))
            for row, file in enumerate(files):
                self.table.setItem(row, 0, QTableWidgetItem(task.toDisplayPath(file)))
                self.table.setItem(row, 1, QTableWidgetItem(toReadableSize(file.size)))
                self.table.setItem(row, 2, QTableWidgetItem())
            self.table.setFixedHeight(self.table.horizontalHeader().height()
                                      + self.table.verticalHeader().length() + 2 * self.table.frameWidth())
        for row, file in enumerate(files):
            self.table.item(row, 2).setText(self._toFileStatusText(file))

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
            InfoCard(task, categoryService, self.scrollWidget),
            ChecksumCard(task, self.scrollWidget),
            ErrorCard(task, self.scrollWidget),
            FileListCard(task, self.scrollWidget),
            *featureService.detailCards(task, self.scrollWidget),
        ]
        self.refreshTimer = QTimer(self)
        self.slideAnimation = QPropertyAnimation(self.widget, b"pos", self)
        self._initWidget()
        self._initLayout()
        self._bind()
        self._refresh()

    def _initWidget(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setClosableOnMaskClicked(True)
        self.setMaskColor(QColor(0, 0, 0, 76))
        self.setShadowEffect(60, (0, 0), QColor(0, 0, 0, 50))
        self._hBoxLayout.removeWidget(self.widget)
        background = "rgb(32, 32, 32)" if isDarkTheme() else "rgb(243, 243, 243)"
        self.widget.setStyleSheet(f"#centerWidget {{ background-color: {background}; border: none; }}")
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollArea.enableTransparentBackground()
        self.scrollWidget.setStyleSheet("background: transparent")
        self.refreshTimer.setInterval(1000)
        self.slideAnimation.setDuration(SLIDE_DURATION)
        self.slideAnimation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _initLayout(self) -> None:
        titleLayout = QHBoxLayout()
        titleLayout.setContentsMargins(24, 20, 16, 8)
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
        self._taskService.taskRemoved.connect(self._onTaskRemoved, owner=self)

    def _refresh(self) -> None:
        for card in self.cards:
            card.refresh()

    def _onTaskRemoved(self, taskId: str) -> None:
        if taskId == self._task.taskId:
            self.reject()

    def _toDrawerWidth(self) -> int:
        return min(DRAWER_MAX_WIDTH, int(self.width() * DRAWER_WIDTH_RATIO))

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.refreshTimer.start()
        width = self._toDrawerWidth()
        self.widget.setGeometry(self.width(), 0, width, self.height())
        self.slideAnimation.setStartValue(QPoint(self.width(), 0))
        self.slideAnimation.setEndValue(QPoint(self.width() - width, 0))
        self.slideAnimation.start()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        width = self._toDrawerWidth()
        self.slideAnimation.stop()
        self.widget.setGeometry(self.width() - width, 0, width, self.height())
