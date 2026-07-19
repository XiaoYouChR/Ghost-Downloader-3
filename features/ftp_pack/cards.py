
from qfluentwidgets import FluentIcon, ToolButton

from app.format import toReadableSize
from app.models.task import TaskStatus
from app.view.cards.draft_cards import UniversalDraftCard
from app.view.cards.task_cards import UniversalTaskCard
from app.view.dialogs.file_select import FileSelectDialog
from .task import FtpTask


def openFileSelection(task: FtpTask, parent, apply=None) -> set[int] | None:
    dialog = FileSelectDialog(task, parent)
    try:
        if not dialog.exec():
            return None
        selectedIndexes = dialog.selectedIndexes()
        (apply or task.setSelection)(selectedIndexes)
        return selectedIndexes
    finally:
        dialog.deleteLater()


class FtpDraftCard(UniversalDraftCard):

    @property
    def task(self) -> FtpTask:
        return self._task

    def _initWidget(self):
        super()._initWidget()
        self._selectFilesButton = None
        if self.task.files and len(self.task.files) > 1:
            from qfluentwidgets import ToolTipFilter
            from qfluentwidgets import TransparentToolButton
            self._selectFilesButton = TransparentToolButton(FluentIcon.LIBRARY, self)
            self._selectFilesButton.setFixedSize(28, 28)
            self._selectFilesButton.setToolTip(self.tr("选择文件"))
            self._selectFilesButton.installEventFilter(ToolTipFilter(self._selectFilesButton))
        self._refreshSummary()

    def _initLayout(self):
        super()._initLayout()
        if self._selectFilesButton is not None:
            self.layout().addWidget(self._selectFilesButton)

    def _bind(self):
        super()._bind()
        if self._selectFilesButton is not None:
            self._selectFilesButton.clicked.connect(self._onSelectFilesClicked)

    def _refreshSummary(self):
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

    def _onSelectFilesClicked(self):
        openFileSelection(self.task, self.window(), apply=self.selectionSubmitted.emit)

    def refresh(self) -> None:
        super().refresh()
        self._refreshSummary()

class FtpTaskCard(UniversalTaskCard):
    def __init__(self, task: FtpTask, parent=None):
        super().__init__(task, parent)
        self.selectFilesButton = None
        if task.files and len(task.files) > 1:
            self.selectFilesButton = ToolButton(FluentIcon.LIBRARY, self)
            self.hBoxLayout.insertWidget(
                self.hBoxLayout.indexOf(self.verifyHashButton),
                self.selectFilesButton,
            )
            self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)

    def refresh(self, force: bool = False) -> None:
        super().refresh(force=force)
        if self.task.status in {TaskStatus.WAITING, TaskStatus.COMPLETED} and self.selectFilesButton is not None and not self._isFileMissing:
            selected = sum(1 for f in self.task.files if f.selected)
            self.statusLabel.setText(self.tr("{0}/{1} 个文件").format(selected, len(self.task.files)))

    def _onSelectFilesClicked(self):
        from app.services.task_service import taskService
        openFileSelection(
            self.task, self.window(),
            apply=lambda indexes: taskService.applySelection(self.task, indexes),
        )
        self.refresh(force=True)
