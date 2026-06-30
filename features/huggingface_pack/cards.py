from __future__ import annotations

from qfluentwidgets import FluentIcon, ToolButton, ToolTipFilter, TransparentToolButton

from app.format import toReadableSize
from app.models.task import TaskStatus
from app.view.cards.draft_cards import UniversalDraftCard
from app.view.cards.task_cards import UniversalTaskCard
from app.view.dialogs.file_select import FileSelectDialog
from .task import HuggingFaceTask


class HuggingFaceDraftCard(UniversalDraftCard):

    @property
    def task(self) -> HuggingFaceTask:
        return self._task

    def _initWidget(self) -> None:
        super()._initWidget()
        self._selectFilesButton = None
        if self.task.files and len(self.task.files) > 1:
            self._selectFilesButton = TransparentToolButton(FluentIcon.LIBRARY, self)
            self._selectFilesButton.setFixedSize(28, 28)
            self._selectFilesButton.setToolTip(self.tr("选择文件"))
            self._selectFilesButton.installEventFilter(ToolTipFilter(self._selectFilesButton))
        self._refreshSummary()

    def _initLayout(self) -> None:
        super()._initLayout()
        if self._selectFilesButton is not None:
            self.layout().addWidget(self._selectFilesButton)

    def _bind(self) -> None:
        super()._bind()
        if self._selectFilesButton is not None:
            self._selectFilesButton.clicked.connect(self._onSelectFilesClicked)

    def _refreshSummary(self) -> None:
        if not self.task.files or len(self.task.files) <= 1:
            self.sizeLabel.setText(toReadableSize(self.task.fileSize))
            return
        self.sizeLabel.setText(
            self.tr("{0}/{1} 个文件 · {2}").format(
                self.task.countSelected,
                len(self.task.files),
                toReadableSize(self.task.fileSize),
            )
        )

    def _onSelectFilesClicked(self) -> None:
        dialog = FileSelectDialog(self.task, self.window())
        try:
            if dialog.exec():
                self.task.setSelection(dialog.selectedIndexes())
                self._refreshSummary()
                self.nameLabel.setText(self.task.name)
        finally:
            dialog.deleteLater()


class HuggingFaceTaskCard(UniversalTaskCard):
    def __init__(self, task: HuggingFaceTask, parent=None):
        super().__init__(task, parent)
        self.selectFilesButton = ToolButton(FluentIcon.LIBRARY, self)
        self.hBoxLayout.insertWidget(
            self.hBoxLayout.indexOf(self.verifyHashButton),
            self.selectFilesButton,
        )
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)

    def refresh(self) -> None:
        super().refresh()
        hasMultipleFiles = self._task.files and len(self._task.files) > 1
        self.selectFilesButton.setVisible(hasMultipleFiles)
        self.selectFilesButton.setEnabled(self._task.status != TaskStatus.RUNNING)

        if self._task.status in {TaskStatus.WAITING, TaskStatus.COMPLETED} and hasMultipleFiles:
            selected = sum(1 for f in self._task.files if f.selected)
            self.statusLabel.setText(self.tr("{0}/{1} 个文件").format(selected, len(self._task.files)))

    def _onSelectFilesClicked(self) -> None:
        if self._task.status == TaskStatus.RUNNING:
            return
        dialog = FileSelectDialog(self._task, self.window())
        try:
            if dialog.exec():
                self._task.setSelection(dialog.selectedIndexes())
        finally:
            dialog.deleteLater()
