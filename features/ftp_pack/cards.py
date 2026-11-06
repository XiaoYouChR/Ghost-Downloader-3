from __future__ import annotations

from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.dialogs.file_select import FileSelectDialog
from .task import FtpTask


class FtpDraftCard(MultiFileDraftCard):
    fileSelectDialog = FileSelectDialog
    _task: FtpTask

    @property
    def task(self) -> FtpTask:
        return self._task


class FtpTaskCard(MultiFileTaskCard):
    fileSelectDialog = FileSelectDialog
    _task: FtpTask

    @property
    def task(self) -> FtpTask:
        return self._task
