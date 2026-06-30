from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    IndeterminateProgressBar, InfoBar, InfoBarPosition,
    MessageBox, MessageBoxBase, SubtitleLabel,
)

from app.format import toReadableSize
from app.view.components.card_groups import OptionCardGroup

if TYPE_CHECKING:
    from app.models.task import Task


class EditTaskDialog(MessageBoxBase):

    def __init__(self, task: Task, cards: list[QWidget], parent=None):
        super().__init__(parent)
        self._task = task

        self.titleLabel = SubtitleLabel(self.tr("编辑任务参数"), self)
        self.cardGroup = OptionCardGroup(self)
        self.progressBar = IndeterminateProgressBar(self)

        self.widget.setMinimumWidth(680)
        self.progressBar.hide()
        self.yesButton.setText(self.tr("应用"))
        self.cancelButton.setText(self.tr("取消"))

        for card in cards:
            self.cardGroup.addCard(card)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.progressBar)
        self.viewLayout.addWidget(self.cardGroup)


class DraftEditDialog(EditTaskDialog):

    def accept(self):
        self._task.setOptions(self.cardGroup.options())
        super().accept()


class LiveEditDialog(EditTaskDialog):

    def __init__(self, task: Task, cards: list[QWidget], parent=None):
        super().__init__(task, cards, parent)
        self._pendingParseId: str = ""

    def accept(self):
        from app.models.task import TaskOptions
        from app.services.coroutine_runner import coroutineRunner
        from app.services.feature_service import featureService

        options = self.cardGroup.options()
        newUrl = options.pop("url", "").strip()

        if not newUrl or newUrl == self._task.url:
            from app.services.task_service import taskService
            taskService.edit(self._task, options)
            super().accept()
            return

        self._setInteractive(False)
        taskOptions = TaskOptions.fromOptions({**options, "url": newUrl})
        self._pendingParseId = coroutineRunner.submit(
            featureService.parse(taskOptions),
            done=self._onReparsed,
            failed=self._onReparseFailed,
            options=options,
            owner=self,
        )

    def reject(self):
        self._cancelPendingParse()
        super().reject()

    def _cancelPendingParse(self, *_args) -> None:
        if not self._pendingParseId:
            return
        from app.services.coroutine_runner import coroutineRunner

        coroutineRunner.cancel(self._pendingParseId)
        self._pendingParseId = ""

    def _setInteractive(self, enabled: bool) -> None:
        self.progressBar.setVisible(not enabled)
        self.yesButton.setEnabled(enabled)

    def _onReparsed(self, newTask: Task, options: dict) -> None:
        from app.services.task_service import taskService

        self._pendingParseId = ""

        if self._task.canReuseProgress(newTask):
            taskService.edit(self._task, options, newTask)
            super().accept()
            return

        receivedBytes = self._task.currentSnapshot()[2]
        if receivedBytes > 0:
            confirm = MessageBox(
                self.tr("确认更换链接"),
                self.tr("新链接与原链接的内容不一致，将清除已下载的 {0} 数据，是否继续？").format(
                    toReadableSize(receivedBytes)
                ),
                self,
            )
            if not confirm.exec():
                self._setInteractive(True)
                return

        taskService.edit(self._task, options, newTask)
        super().accept()

    def _onReparseFailed(self, error: str, **_) -> None:
        self._pendingParseId = ""
        self._setInteractive(True)
        InfoBar.error(
            title=self.tr("链接解析失败"),
            content=error,
            duration=4000,
            position=InfoBarPosition.TOP,
            parent=self,
        )
