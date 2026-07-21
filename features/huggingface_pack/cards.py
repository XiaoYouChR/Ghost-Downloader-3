from __future__ import annotations

from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.dialogs.file_select import FileSelectDialog
from .task import HuggingFaceTask


class HuggingFaceDraftCard(MultiFileDraftCard):

    @property
    def task(self) -> HuggingFaceTask:
        return self._task

    def _onSelectFilesClicked(self) -> None:
        dialog = FileSelectDialog(self.task, self.window())
        try:
            if dialog.exec():
                self.task.setSelection(dialog.selectedIndexes())
                self._refreshSummary()
                self.nameLabel.setText(self.task.name)
        finally:
            dialog.deleteLater()


class HuggingFaceTaskCard(MultiFileTaskCard):

    def _onSelectFilesClicked(self) -> None:
        dialog = FileSelectDialog(self._task, self.window())
        try:
            if dialog.exec():
                self._taskService.applySelection(self._task, dialog.selectedIndexes())
                self.refresh(force=True)
        finally:
            dialog.deleteLater()
