from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QFileInfo, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileIconProvider, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, IndeterminateProgressBar, ProgressBar, PushButton, StrongBodyLabel,
)

from app.format import toReadableSize
from app.models.task import SpecialFileSize, TaskStatus
from app.platform.desktop_notification import (
    FILE_ICON_SIZE, ICON_SPACING, PADDING, SPACING, TEXT_WIDTH, NotificationPopup, Popup, PopupStack,
)
from app.view.cards.task_cards import toEtaText, toSizeText

if TYPE_CHECKING:
    from desktop_notifier.common import Notification

    from app.models.task import Task
    from app.services.task_service import TaskService

MAX_TASK_POPUPS = 3


class TaskPopup(Popup):
    hasTaskbarButton = True

    def __init__(self, task: Task, start: Callable[[Task], None], pause: Callable[[Task], None],
                 delete: Callable[[Task], None]):
        super().__init__()
        self._task = task
        self._start = start
        self._pause = pause
        self._delete = delete
        self._initWidget()
        self._initLayout()
        self._bind()
        self.refresh()
        self.refreshTimer.start()

    def _initWidget(self) -> None:
        super()._initWidget()
        self.setWindowTitle(self._task.name)
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

        self.refreshTimer = QTimer(self)
        self.refreshTimer.setInterval(1000)

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
        self.minimizeButton.clicked.connect(self.showMinimized)
        self.toggleButton.clicked.connect(self._onToggleClicked)
        self.cancelButton.clicked.connect(lambda: self._delete(self._task))
        self.refreshTimer.timeout.connect(self.refresh)

    def refresh(self) -> None:
        task = self._task
        progress, speed, received = task.currentSnapshot()
        if task.status == TaskStatus.RUNNING:
            self.statusLabel.setText(f"{toReadableSize(speed)}/s · {toEtaText(task, speed, received)}")
        elif task.status == TaskStatus.PAUSED:
            self.statusLabel.setText(self.tr("任务已经暂停"))
        else:
            self.statusLabel.setText(self.tr("任务正在等待"))
        self.sizeLabel.setText(toSizeText(task, speed, received) or "")

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

    def _onToggleClicked(self) -> None:
        if self._task.status == TaskStatus.PAUSED:
            self._start(self._task)
        else:
            self._pause(self._task)
        self.refresh()


class TaskTracker:
    """在 TaskService.resumeSaved 之后创建，使 Saved Tasks 不显示 Task Popup。"""

    def __init__(self, taskService: TaskService, stack: PopupStack, isEnabled: Callable[[], bool],
                 buildResult: Callable[[Task], Notification]):
        self._taskService = taskService
        self._stack = stack
        self._isEnabled = isEnabled
        self._buildResult = buildResult
        self._candidateIds: set[str] = set()
        self._popups: dict[str, Popup] = {}
        taskService.taskAdded.connect(self._onTaskAdded)
        taskService.taskStarted.connect(self._onTaskStarted)
        taskService.taskCompleted.connect(self._onTaskEnded)
        taskService.taskFailed.connect(self._onTaskEnded)
        taskService.taskRemoved.connect(self._onTaskRemoved)

    def isTracking(self, taskId: str) -> bool:
        return taskId in self._popups

    def _track(self, taskId: str, popup: Popup, replacing: Popup | None = None) -> None:
        self._popups[taskId] = popup
        popup.exited.connect(lambda: self._untrack(taskId, popup))
        self._stack.add(popup, replacing)

    def _untrack(self, taskId: str, popup: Popup) -> None:
        if self._popups.get(taskId) is popup:
            del self._popups[taskId]

    def _onTaskAdded(self, task: Task) -> None:
        self._candidateIds.add(task.taskId)

    def _onTaskStarted(self, task: Task) -> None:
        if task.taskId not in self._candidateIds:
            return
        self._candidateIds.discard(task.taskId)
        if self._isEnabled() and len(self._popups) < MAX_TASK_POPUPS:
            self._track(task.taskId, TaskPopup(
                task, self._taskService.start, self._taskService.pause,
                lambda t: self._taskService.delete(t, shouldDeleteFiles=True)))

    def _onTaskEnded(self, task: Task) -> None:
        if (popup := self._popups.get(task.taskId)) is not None:
            self._track(task.taskId, NotificationPopup(self._buildResult(task)), replacing=popup)

    def _onTaskRemoved(self, taskId: str) -> None:
        self._candidateIds.discard(taskId)
        if (popup := self._popups.pop(taskId, None)) is not None:
            popup.exit(isDismissed=False)
