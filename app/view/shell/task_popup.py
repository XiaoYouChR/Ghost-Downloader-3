from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QFileInfo, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileIconProvider, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, IndeterminateProgressBar, ProgressBar, PushButton, StrongBodyLabel,
)

from app.format import toReadableSize
from app.models.task import SpecialFileSize, TaskStatus
from app.platform.desktop_notification import (
    FILE_ICON_SIZE, ICON_SPACING, PADDING, SPACING, TEXT_WIDTH, Popup,
)


def toRemainingText(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} 秒"
    minutes, secs = divmod(seconds, 60)
    if seconds < 3600:
        return f"{minutes} 分 {secs} 秒" if secs else f"{minutes} 分"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小时 {minutes} 分" if minutes else f"{hours} 小时"


if TYPE_CHECKING:
    from app.models.task import Task
    from app.services.task_service import TaskService
    from app.signal import Signal

class TaskPopup(Popup):
    hasTaskbarButton = True

    def __init__(self, task: Task, taskService: TaskService, speedChanged: Signal):
        super().__init__()
        self._task = task
        self._taskService = taskService
        self._speedChanged = speedChanged
        self.popupId = f"task:{task.taskId}"
        self._initWidget()
        self._initLayout()
        self._bind()
        self.refresh()

    def _initWidget(self) -> None:
        self.setWindowIcon(QFileIconProvider().icon(QFileInfo(self._task.outputPath)))
        super()._initWidget()
        self.setWindowTitle(self._task.name)
        if sys.platform == "win32":
            from app.config.constants import DESKTOP_ID
            from app.platform.taskbar import setWindowAppId
            setWindowAppId(int(self.winId()), f"{DESKTOP_ID}.{self._task.taskId.replace('_', '-')}")
        self.minimizeButton = self._createHeaderButton(FluentIcon.MINIMIZE)
        self.headerButtons.insert(0, self.minimizeButton)

        self.iconLabel = QLabel(self)
        self.iconLabel.setPixmap(self._toPixmap(
            QFileIconProvider().icon(QFileInfo(self._task.outputPath)).pixmap(FILE_ICON_SIZE, FILE_ICON_SIZE),
            FILE_ICON_SIZE))
        self.nameLabel = StrongBodyLabel(self)
        self.nameLabel.setText(self.nameLabel.fontMetrics().elidedText(
            self._task.name, Qt.TextElideMode.ElideMiddle, TEXT_WIDTH))
        self.nameLabel.setToolTip(self._task.name)
        self.statusLabel = BodyLabel(self)
        self.sizeLabel = CaptionLabel(self)
        self.sizeLabel.setTextColor(QColor(0, 0, 0, 155), QColor(255, 255, 255, 155))
        if self._task.fileSize in {SpecialFileSize.UNKNOWN, SpecialFileSize.NOT_SUPPORTED}:
            self.progressBar = IndeterminateProgressBar(self)
        else:
            self.progressBar = ProgressBar(self)
        self.toggleButton = PushButton(self)
        self.cancelButton = PushButton(self.tr("取消"), self)
        for button in (self.toggleButton, self.cancelButton):
            button.setFixedHeight(32)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _initLayout(self) -> None:
        super()._initLayout()
        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        texts.addWidget(self.nameLabel)
        texts.addWidget(self.statusLabel)
        texts.addWidget(self.sizeLabel)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, PADDING // 2, 0)
        content.setSpacing(ICON_SPACING)
        content.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignTop)
        content.addLayout(texts, 1)
        self.vBoxLayout.addLayout(content)

        bottom = QVBoxLayout()
        bottom.setContentsMargins(0, SPACING, PADDING // 2, 0)
        bottom.setSpacing(SPACING * 2)
        bottom.addWidget(self.progressBar)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(SPACING)
        buttons.addWidget(self.toggleButton)
        buttons.addWidget(self.cancelButton)
        bottom.addLayout(buttons)
        self.vBoxLayout.addLayout(bottom)
        self.adjustSize()

    def _bind(self) -> None:
        super()._bind()
        self.minimizeButton.clicked.connect(self._onMinimizeClicked)
        self.toggleButton.clicked.connect(self._onToggleClicked)
        self.cancelButton.clicked.connect(lambda: self._taskService.delete(self._task, shouldDeleteFiles=True))
        self._speedChanged.connect(self.refresh, owner=self)
        self._taskService.taskPaused.connect(self._onTaskPaused, owner=self)
        self._taskService.taskStarted.connect(self._onTaskStarted, owner=self)

    def refresh(self, _speed: int | None = None) -> None:
        task = self._task
        progress, speed, received = task.currentSnapshot()
        if task.status == TaskStatus.RUNNING and speed > 0 and task.fileSize > 0:
            remaining = int((task.fileSize - received) / speed)
            self.statusLabel.setText(self.tr("速度 {0}/s，剩余 {1}").format(
                toReadableSize(speed), toRemainingText(remaining)))
        elif task.status == TaskStatus.RUNNING and speed > 0:
            self.statusLabel.setText(self.tr("速度 {0}/s").format(toReadableSize(speed)))
        elif task.status == TaskStatus.RUNNING:
            self.statusLabel.setText(self.tr("正在计算速度"))
        elif task.status == TaskStatus.PAUSED:
            self.statusLabel.setText(self.tr("任务已经暂停"))
        else:
            self.statusLabel.setText(self.tr("任务正在等待"))
        if task.fileSize > 0:
            self.sizeLabel.setText(self.tr("已下载 {0}，共 {1}").format(
                toReadableSize(received), toReadableSize(task.fileSize)))
        else:
            self.sizeLabel.setText(self.tr("已下载 {0}").format(toReadableSize(received)))

        isPaused = task.status == TaskStatus.PAUSED
        if isinstance(self.progressBar, ProgressBar):
            self.progressBar.setValue(int(progress))
        if isPaused:
            self.progressBar.pause()
        else:
            self.progressBar.resume()
        self.toggleButton.setText(self.tr("继续") if isPaused else self.tr("暂停"))
        self.toggleButton.setEnabled(isPaused or task.canPause)

        if sys.platform == "win32":
            from app.platform.taskbar import setWindowsProgress
            isKnown = isinstance(self.progressBar, ProgressBar)
            setWindowsProgress(int(self.winId()), task.status, progress if isKnown else None)

    def _onTaskPaused(self, task: Task) -> None:
        if task.taskId == self._task.taskId:
            self.refresh()

    def _onTaskStarted(self, task: Task) -> None:
        if task.taskId == self._task.taskId:
            self.refresh()

    def _onMinimizeClicked(self) -> None:
        if sys.platform != "win32":
            self.showMinimized()
            return
        from app.platform.taskbar import minimizeWithoutActivating
        pos = self._targetPos
        minimizeWithoutActivating(int(self.winId()), pos.x(), pos.y(), self.width(), self.height())

    def _onToggleClicked(self) -> None:
        if self._task.status == TaskStatus.PAUSED:
            self._taskService.start(self._task)
        else:
            self._taskService.pause(self._task)
        self.refresh()
