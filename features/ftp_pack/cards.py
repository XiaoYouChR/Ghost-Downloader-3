from __future__ import annotations

from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.dialogs.file_select import FileSelectDialog
from .task import FtpTask


class FtpDraftCard(MultiFileDraftCard):

    @property
    def task(self) -> FtpTask:
        return self._task

    def _onSelectFilesClicked(self):
        dialog = FileSelectDialog(self.task, self.window())
        try:
            if dialog.exec():
                self.task.setSelection(dialog.selectedIndexes())
                self._refreshSummary()
        finally:
            dialog.deleteLater()

class FtpTaskCard(MultiFileTaskCard):

    def _onSelectFilesClicked(self):
        openFileSelection(
            self._task, self.window(),
            apply=lambda indexes: self._taskService.applySelection(self._task, indexes),
        )
        self.refresh(force=True)
