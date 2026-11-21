from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from qfluentwidgets import BodyLabel, ComboBox, LineEdit, MessageBoxBase, PushButton, SubtitleLabel

from app.format import toReadableSize
from app.i18n import toLocalizedError
from app.models.task import TaskStatus, toHost

if TYPE_CHECKING:
    from app.models.task import Task, TaskError
    from app.services.task_service import TaskService


class SourceChoiceDialog(MessageBoxBase):
    def __init__(self, incoming: Task, targets: list[Task], taskService: TaskService, parent=None):
        super().__init__(parent)
        self._incoming = incoming
        self._taskService = taskService
        self._target: Task | None = None
        self.shouldCreateTask = False
        self.titleLabel = SubtitleLabel(self.tr("选择下载方式"), self)
        self.fileLabel = BodyLabel(f"{incoming.name}  ·  {toReadableSize(incoming.fileSize)}  ·  {toHost(incoming.url)}", self)
        self.targetBox = ComboBox(self)
        self.sha256Edit = LineEdit(self)
        self.statusLabel = BodyLabel(self)
        self.newTaskButton = PushButton(self.tr("新建任务"), self.buttonGroup)
        self._initWidget(targets)
        self._initLayout()
        self._bind()

    def _initWidget(self, targets: list[Task]) -> None:
        self.widget.setFixedWidth(570)
        self.fileLabel.setWordWrap(True)
        self.fileLabel.setTextFormat(Qt.TextFormat.PlainText)
        self.statusLabel.setWordWrap(True)
        self.statusLabel.setTextFormat(Qt.TextFormat.PlainText)
        self.statusLabel.hide()
        self.yesButton.setText(self.tr("添加到现有任务"))
        self.cancelButton.setText(self.tr("取消"))
        self.targetBox.setAccessibleName(self.tr("现有任务"))
        for task in targets:
            status = self.tr("已暂停") if task.status == TaskStatus.PAUSED else self.tr("下载中")
            progress, _, _ = task.currentSnapshot()
            label = f"{status}  {progress:.1f}%  ·  {task.outputPath}"
            label = self.targetBox.fontMetrics().elidedText(label, Qt.TextElideMode.ElideMiddle, 460)
            self.targetBox.addItem(label, userData=task.taskId)
        self.sha256Edit.setPlaceholderText(self.tr("可信的 SHA-256（可选）"))
        self._onTargetChanged()

    def _initLayout(self) -> None:
        for widget in (self.titleLabel, self.fileLabel, self.targetBox, self.sha256Edit, self.statusLabel):
            self.viewLayout.addWidget(widget)
        self.buttonLayout.insertWidget(1, self.newTaskButton, 1)

    def _bind(self) -> None:
        self.newTaskButton.clicked.connect(self._onNewTaskClicked)
        self.targetBox.currentIndexChanged.connect(self._onTargetChanged)
        self._taskService.sourceAdded.connect(self._onSourceAdded, owner=self)
        self._taskService.sourceAddFailed.connect(self._onSourceAddFailed, owner=self)

    def validate(self) -> bool:
        if self._target is not None:
            return False
        target = self._taskService.taskById(self.targetBox.currentData())
        if target is None or not target.canAddSource(self._incoming):
            self.statusLabel.setText(self.tr("该任务已变更，请选择其他任务或新建任务。"))
            self.statusLabel.show()
            return False
        self._target = target
        self.statusLabel.setText(self.tr("正在验证两个下载源的文件样本…"))
        self.statusLabel.show()
        self._setBusy(True)
        self._taskService.addSource(target, self._incoming, self.sha256Edit.text())
        return False

    def reject(self) -> None:
        if self._target is None:
            super().reject()

    def _setBusy(self, isBusy: bool) -> None:
        for widget in (self.targetBox, self.sha256Edit, self.yesButton, self.newTaskButton, self.cancelButton):
            widget.setEnabled(not isBusy)

    def _onNewTaskClicked(self) -> None:
        self.shouldCreateTask = True
        self.reject()

    def _onTargetChanged(self) -> None:
        target = self._taskService.taskById(self.targetBox.currentData())
        self.targetBox.setToolTip(target.outputPath if target is not None else "")

    def _onSourceAdded(self, target: Task, incoming: Task) -> None:
        if target is self._target and incoming is self._incoming:
            self.accept()

    def _onSourceAddFailed(self, target: Task, incoming: Task, error: TaskError) -> None:
        if target is self._target and incoming is self._incoming:
            self._target = None
            self.statusLabel.setText(toLocalizedError(error))
            self._setBusy(False)
