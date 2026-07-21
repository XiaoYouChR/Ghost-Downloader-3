from PySide6.QtWidgets import QFileIconProvider
from qfluentwidgets import FluentIcon

from app.format import toReadableSize, toReadableTime
from app.models.task import TaskStatus
from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.components.labels import IconBodyLabel
from app.view.dialogs.file_select import FileSelectDialog
from .task import BTTask


def openFileSelection(task: BTTask, parent, apply=None) -> set[int] | None:
    dialog = TorrentFileSelectDialog(task, parent)
    try:
        if not dialog.exec():
            return None
        selectedIndexes = dialog.selectedIndexes()
        (apply or task.setSelection)(selectedIndexes)
        return selectedIndexes
    finally:
        dialog.deleteLater()


class TorrentFileSelectDialog(FileSelectDialog):
    def _fileDisplayPath(self, file) -> str:
        return self._task.toRelativePath(file)


class BTDraftCard(MultiFileDraftCard):

    @property
    def task(self) -> BTTask:
        return self._task

    def _initWidget(self):
        super()._initWidget()
        icon = QFileIconProvider.IconType.File if self.task.isSingleFile else QFileIconProvider.IconType.Folder
        self.iconLabel.setImage(QFileIconProvider().icon(icon).pixmap(16, 16))
        self.iconLabel.setFixedSize(16, 16)

    def _onSelectFilesClicked(self):
        if openFileSelection(self.task, self.window()) is not None:
            self._refreshSummary()


class BTTaskCard(MultiFileTaskCard):

    def _initWidget(self):
        super()._initWidget()
        self.speedLabel.setIcon(FluentIcon.DOWNLOAD)
        self.uploadLabel = IconBodyLabel("", FluentIcon.SHARE, self)
        self.uploadLabel.hide()

    def _infoWidgets(self):
        return [self.uploadLabel]

    def _onSelectFilesClicked(self):
        openFileSelection(
            self._task, self.window(),
            apply=lambda indexes: self._taskService.applySelection(self._task, indexes),
        )
        self.refresh(force=True)

    def refresh(self, force=False):
        task: BTTask = self._task
        if not force and self._lastStatus == task.status and task.status != TaskStatus.RUNNING:
            return

        if task.status == TaskStatus.RUNNING:
            progress, speed, receivedBytes = task.currentSnapshot()
            self.progressBar.setValue(int(progress))
            self.progressBar.setError(False)
            if task.fileSize > 0:
                self.sizeLabel.setText(f"{toReadableSize(receivedBytes)}/{toReadableSize(task.fileSize)}")
            else:
                self.sizeLabel.setText(f"{toReadableSize(receivedBytes)}/--")

            if task.isSeeding:
                self._refreshSeeding(task)
            else:
                self._refreshDownloading(task)

            self._refreshButtons()
            self._lastStatus = task.status
        else:
            self.uploadLabel.hide()
            super().refresh(force)
            btStatus = self._seedingSummary(task)
            if btStatus and not self._isFileMissing:
                self.statusLabel.setText(btStatus)

    def _refreshDownloading(self, task: BTTask):
        self.statusLabel.hide()
        self.progressBar.show()
        self.speedLabel.setText(f"{toReadableSize(task.downloadRate)}/s")
        self.speedLabel.show()
        self.uploadLabel.setText(f"{toReadableSize(task.uploadRate)}/s")
        self.uploadLabel.show()
        self.sizeLabel.show()
        if task.fileSize > 0 and task.downloadRate > 0:
            remaining = task.fileSize - task.step.receivedBytes
            self.etaLabel.setText(toReadableTime(int(remaining / task.downloadRate)))
        else:
            self.etaLabel.setText("--")
        self.etaLabel.show()

    def _refreshSeeding(self, task: BTTask):
        self.speedLabel.hide()
        self.etaLabel.hide()
        self.sizeLabel.hide()
        self.progressBar.hide()
        self.uploadLabel.setText(f"{toReadableSize(task.uploadRate)}/s")
        self.uploadLabel.show()
        parts = []
        if task.shareRatioPercent > 0:
            parts.append(self.tr("分享率 {0}").format(f"{task.shareRatioPercent:.1f}%"))
        if task.seedingTimeSeconds > 0:
            parts.append(self.tr("做种 {0}").format(toReadableTime(task.seedingTimeSeconds)))
        if task.peerCount > 0:
            parts.append(self.tr("{0} peers").format(task.peerCount))
        self.statusLabel.setText(self.tr("做种中") + "  " + " · ".join(parts))
        self.statusLabel.show()

    def _seedingSummary(self, task: BTTask) -> str:
        parts: list[str] = []
        if task.stateText and task.stateText not in (
            "下载中", "做种中", "检查续传状态", "校验已有文件",
            "获取元数据", "分配文件中", "等待校验", "下载完成",
        ):
            parts.append(task.stateText)
        if task.shareRatioPercent > 0:
            parts.append(self.tr("分享率 {0}").format(f"{task.shareRatioPercent:.1f}%"))
        if task.seedingTimeSeconds > 0:
            parts.append(self.tr("做种 {0}").format(toReadableTime(task.seedingTimeSeconds)))
        return " · ".join(parts)
