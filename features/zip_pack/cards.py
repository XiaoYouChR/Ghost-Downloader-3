from __future__ import annotations

from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.dialogs.file_select import FileSelectDialog


class ZipDraftCard(MultiFileDraftCard):
    fileSelectDialog = FileSelectDialog


class ZipTaskCard(MultiFileTaskCard):
    fileSelectDialog = FileSelectDialog
