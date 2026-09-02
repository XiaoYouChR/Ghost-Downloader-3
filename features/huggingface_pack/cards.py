from __future__ import annotations

from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.dialogs.file_select import FileSelectDialog
from .task import HuggingFaceTask


class HuggingFaceDraftCard(MultiFileDraftCard):
    fileSelectDialog = FileSelectDialog

    @property
    def task(self) -> HuggingFaceTask:
        return self._task


class HuggingFaceTaskCard(MultiFileTaskCard):
    fileSelectDialog = FileSelectDialog
