from __future__ import annotations

from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.dialogs.file_select import FileSelectDialog


class FtpDraftCard(MultiFileDraftCard):
    fileSelectDialog = FileSelectDialog


class FtpTaskCard(MultiFileTaskCard):
    fileSelectDialog = FileSelectDialog
