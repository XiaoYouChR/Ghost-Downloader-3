
from PySide6.QtWidgets import QFileIconProvider
from qfluentwidgets import FluentIcon, ToolButton

from app.format import toReadableSize, toReadableTime
from app.models.task import TaskStatus
from app.view.cards.draft_cards import UniversalDraftCard
from app.view.cards.task_cards import UniversalTaskCard
from app.view.dialogs.file_select import FileSelectDialog
from .session import btSession
from .task import BTTask


def openFileSelection(task: BTTask, parent) -> set[int] | None:
    dialog = TorrentFileSelectDialog(task, parent)
    try:
        if not dialog.exec():
            return None
        selectedIndexes = dialog.selectedIndexes()
        task.setSelection(selectedIndexes)
        return selectedIndexes
    finally:
        dialog.deleteLater()


class TorrentFileSelectDialog(FileSelectDialog):
    def _fileDisplayPath(self, file) -> str:
        return self._task.toRelativePath(file)


class BTDraftCard(UniversalDraftCard):

    @property
    def task(self) -> BTTask:
        return self._task

    def _initWidget(self):
        super()._initWidget()
        icon = QFileIconProvider.IconType.File if self.task.isSingleFile else QFileIconProvider.IconType.Folder
        self.iconLabel.setImage(QFileIconProvider().icon(icon).pixmap(16, 16))
        self.iconLabel.setFixedSize(16, 16)
        self._selectFilesButton = None
        if len(self.task.files) > 1:
            from qfluentwidgets import ToolTipFilter
            from qfluentwidgets import TransparentToolButton
            self._selectFilesButton = TransparentToolButton(FluentIcon.LIBRARY, self)
            self._selectFilesButton.setFixedSize(28, 28)
            self._selectFilesButton.setToolTip(self.tr("选择文件"))
            self._selectFilesButton.installEventFilter(ToolTipFilter(self._selectFilesButton))

    def _initLayout(self):
        super()._initLayout()
        if self._selectFilesButton is not None:
            self.layout().addWidget(self._selectFilesButton)

    def _bind(self):
        super()._bind()
        if self._selectFilesButton is not None:
            self._selectFilesButton.clicked.connect(self._onSelectFilesClicked)

    def _refreshSummary(self):
        self.sizeLabel.setText(
            self.tr("{0}/{1} 个文件 · {2}").format(
                self.task.countSelected,
                len(self.task.files),
                toReadableSize(self.task.fileSize),
            )
        )

    def _onSelectFilesClicked(self):
        if openFileSelection(self.task, self.window()) is not None:
            self._refreshSummary()


class BTTaskCard(UniversalTaskCard):
    def __init__(self, task: BTTask, parent=None):
        super().__init__(task, parent)
        self.selectFilesButton = ToolButton(FluentIcon.LIBRARY, self)
        self.hBoxLayout.insertWidget(
            self.hBoxLayout.indexOf(self.verifyHashButton),
            self.selectFilesButton,
        )
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)
        btSession.seedingUpdated.connect(self._onSeedingUpdated)

    def _refreshTransferInfo(self):
        task = self.task
        if task.status == TaskStatus.RUNNING:
            self.speedLabel.setText(f"{toReadableSize(task.downloadRate)}/s")
            if task.fileSize > 0 and task.downloadRate > 0 and not task.isSeeding:
                remaining = task.fileSize - task.step.receivedBytes
                self.etaLabel.setText(toReadableTime(int(remaining / task.downloadRate)))
            self.speedLabel.show()
        elif task.status == TaskStatus.COMPLETED and task.isSeeding:
            parts = [f"↑ {toReadableSize(task.uploadRate)}/s"]
            parts.append(self.tr("分享率 {0}").format(f"{task.shareRatioPercent:.1f}%"))
            if task.peerCount > 0:
                parts.append(self.tr("{0} peers").format(task.peerCount))
            self.statusLabel.setText(self.tr("做种中") + "  " + "  ".join(parts))

    def _onSeedingUpdated(self):
        if self.task.status == TaskStatus.COMPLETED and self.task.isSeeding:
            self._refreshTransferInfo()

    def _onSelectFilesClicked(self):
        previousSelected = {f.index for f in self.task.files if f.selected}
        selectedIndexes = openFileSelection(self.task, self.window())
        if selectedIndexes is None:
            return
        self._refreshTransferInfo()

    def refresh(self):
        super().refresh()
        self._refreshTransferInfo()
        self.selectFilesButton.setEnabled(
            self.task.status != TaskStatus.COMPLETED or any(not f.selected for f in self.task.files)
        )
