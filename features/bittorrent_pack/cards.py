from PySide6.QtWidgets import QFileIconProvider
from qfluentwidgets import FluentIcon

from app.format import toReadableSize, toReadableTime
from app.models.task import TaskStatus
from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard, FieldSpec, toSizeText
from app.view.components.labels import IconBodyLabel
from app.view.dialogs.file_select import FileSelectDialog
from .task import BTTask


class TorrentFileSelectDialog(FileSelectDialog):
    def _fileDisplayPath(self, file) -> str:
        return self._task.toRelativePath(file)


def toBtEtaText(task: BTTask, speed: int, received: int) -> str | None:
    if task.isSeeding:
        return None
    if task.fileSize > 0 and speed > 0:
        return toReadableTime(int((task.fileSize - received) / speed))
    return "--"


def toBtSizeText(task: BTTask, speed: int, received: int) -> str | None:
    if task.status == TaskStatus.RUNNING and task.isSeeding:
        return None
    return toSizeText(task, speed, received)


BT_SPEED_FIELD = FieldSpec("speed", FluentIcon.DOWNLOAD, {
    TaskStatus.RUNNING: lambda t, s, r: None if t.isSeeding else f"{toReadableSize(s)}/s",
})
BT_UPLOAD_FIELD = FieldSpec("upload", FluentIcon.SHARE, {
    TaskStatus.RUNNING: lambda t, s, r: f"{toReadableSize(t.uploadRate)}/s",
})
BT_ETA_FIELD = FieldSpec("eta", FluentIcon.STOP_WATCH, {TaskStatus.RUNNING: toBtEtaText})
BT_SIZE_FIELD = FieldSpec("size", FluentIcon.LIBRARY, {None: toBtSizeText})


def toBtNameText(task: BTTask, speed: int, received: int) -> str | None:
    if not task.isSeeding and task.stateText:
        return f"{task.name} ({task.stateText})"
    return None


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
        dialog = TorrentFileSelectDialog(self.task, self.window())
        try:
            if dialog.exec():
                self.task.setSelection(dialog.selectedIndexes())
                self._refreshSummary()
        finally:
            dialog.deleteLater()


class BTTaskCard(MultiFileTaskCard):
    uploadLabel: IconBodyLabel
    fileSelectDialog = TorrentFileSelectDialog
    infoFields = [BT_SPEED_FIELD, BT_UPLOAD_FIELD, BT_ETA_FIELD, BT_SIZE_FIELD]
    nameFormats = {TaskStatus.RUNNING: toBtNameText}

    def _refreshForStatus(self, task):
        super()._refreshForStatus(task)
        if task.status == TaskStatus.RUNNING and task.isSeeding:
            self.progressBar.hide()
            parts = []
            if task.shareRatioPercent > 0:
                parts.append(self.tr("分享率 {0}").format(f"{task.shareRatioPercent:.1f}%"))
            if task.seedingTimeSeconds > 0:
                parts.append(self.tr("做种 {0}").format(toReadableTime(task.seedingTimeSeconds)))
            if task.peerCount > 0:
                parts.append(self.tr("{0} peers").format(task.peerCount))
            self._setStatus(self.tr("做种中") + "  " + " · ".join(parts))
        elif task.status != TaskStatus.RUNNING:
            parts = []
            if task.stateText and task.stateText not in (
                "下载中", "做种中", "检查续传状态", "校验已有文件",
                "获取元数据", "分配文件中", "等待校验", "下载完成",
            ):
                parts.append(task.stateText)
            if task.shareRatioPercent > 0:
                parts.append(self.tr("分享率 {0}").format(f"{task.shareRatioPercent:.1f}%"))
            if task.seedingTimeSeconds > 0:
                parts.append(self.tr("做种 {0}").format(toReadableTime(task.seedingTimeSeconds)))
            summary = " · ".join(parts)
            if summary and not self._isFileMissing:
                self.statusLabel.setText(summary)
