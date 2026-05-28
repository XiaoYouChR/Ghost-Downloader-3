from typing import Literal

from PySide6.QtCore import Signal
from qfluentwidgets import (
    IndeterminateProgressBar,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    MessageBoxBase,
    SubtitleLabel,
)

from app.bases.models import Task, TaskStatus
from app.services.core_service import coreService
from app.supports.utils import toReadableSize
from app.view.components.card_widgets import ParseSettingHeaderCardWidget


EditContext = Literal["result", "task"]


class EditTaskDialog(MessageBoxBase):
    # context="result" 和 "task" 的差别只体现在 url 改动: result 流程让 textarea 重新接管
    # (避免在 AddTaskDialog 内再开一条 parse 管线), task 流程才在 Dialog 内异步 re-parse

    urlReplaced = Signal(str, str)

    def __init__(self, task: Task, context: EditContext, parent=None) -> None:
        super().__init__(parent)

        self._task = task
        self._context = context
        self._pendingParseId = ""
        self._resumeOnAccept = False

        # instant widget
        self.titleLabel = SubtitleLabel(self.tr("编辑任务参数"), self)
        self.cardGroup = ParseSettingHeaderCardWidget(self)
        self.progressBar = IndeterminateProgressBar(self)

        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.setObjectName("EditTaskDialog")
        self.widget.setMinimumWidth(680)
        self.progressBar.hide()
        self.yesButton.setText(self.tr("应用"))
        self.cancelButton.setText(self.tr("取消"))

        for card in self._task.editorCards(self):
            self.cardGroup.addCard(card)

    def _initLayout(self) -> None:
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.progressBar)
        self.viewLayout.addWidget(self.cardGroup)

    def exec(self) -> int:
        # RUNNING 任务进 Dialog 前自动 pause; accept 时 resume, cancel 时保持 pause
        if self._task.status == TaskStatus.RUNNING and self._task.canPause:
            self._resumeOnAccept = True
            coreService.stopTask(self._task)
        return super().exec()

    def accept(self) -> None:
        # 拦截 MessageBoxBase 的同步 accept — URL 改了要等 re-parse 回来再决定关不关
        payload = dict(self.cardGroup.payload)
        if "url" in payload:
            payload["url"] = payload["url"].strip()

        newUrl = payload.get("url", "")
        if not newUrl or newUrl == self._task.url:
            self._task.applySettings(payload)
            self._closeAccepted()
            return

        if self._context == "result":
            self.urlReplaced.emit(self._task.url, newUrl)
            self._closeAccepted()
            return

        self._setBusy(True)
        self._pendingParseId = coreService.runCoroutine(
            coreService._parse(payload),
            self._onReparseFinished,
        )

    def reject(self) -> None:
        if self._pendingParseId:
            coreService.cancelCallback(self._pendingParseId)
            self._pendingParseId = ""
        super().reject()

    def _onReparseFinished(self, newTask: Task | None, error: str | None = None) -> None:
        self._pendingParseId = ""
        if error or newTask is None:
            self._setBusy(False)
            InfoBar.error(
                title=self.tr("链接解析失败"),
                content=error or self.tr("解析新链接时发生错误"),
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        if self._task.tryKeepProgress(newTask):
            self._closeAccepted()
            return

        receivedBytes = self._task.currentSnapshot()[2]
        if receivedBytes > 0:
            confirmDialog = MessageBox(
                self.tr("确认更换链接"),
                self.tr("新链接与原链接的内容不一致，将清除已下载的 {0} 数据，是否继续？").format(
                    toReadableSize(receivedBytes)
                ),
                self,
            )
            if not confirmDialog.exec():
                self._setBusy(False)
                return

        self._task.replaceWith(newTask)
        self._closeAccepted()

    def _setBusy(self, busy: bool) -> None:
        self.progressBar.setVisible(busy)
        self.yesButton.setEnabled(not busy)
        for card in self.cardGroup.cards:
            card.setEnabled(not busy)

    def _closeAccepted(self) -> None:
        if self._resumeOnAccept:
            coreService.createTask(self._task)
        super().accept()
