from __future__ import annotations

from typing import TYPE_CHECKING

from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.dialogs.file_select import FileSelectDialog

if TYPE_CHECKING:
    from .task import ZipTask


class ZipDraftCard(MultiFileDraftCard):
    _task: ZipTask
    fileSelectDialog = FileSelectDialog

    @property
    def task(self) -> ZipTask:
        return self._task


class ZipTaskCard(MultiFileTaskCard):
    _task: ZipTask
    fileSelectDialog = FileSelectDialog

    @property
    def task(self) -> ZipTask:
        return self._task
