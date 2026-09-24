from PySide6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP as N
from PySide6.QtWidgets import QFileIconProvider
from qfluentwidgets import FluentIcon

from app.format import toReadableSize, toReadableTime
from app.models.task import TaskStatus
from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import ETA_FIELD, SIZE_FIELD, FieldSpec, MultiFileTaskCard
from app.view.components.labels import IconBodyLabel
from app.view.dialogs.file_select import FileSelectDialog
from .task import BTTask


class TorrentFileSelectDialog(FileSelectDialog):
    def _fileDisplayPath(self, file) -> str:
        return self._task.toRelativePath(file)


def toUploadText(task: BTTask, _speed: int, _received: int) -> str:
    return f"{toReadableSize(task.uploadRate)}/s"


BT_SPEED_FIELD = FieldSpec("speed", FluentIcon.DOWNLOAD, {
    TaskStatus.RUNNING: lambda t, s, r: f"{toReadableSize(s)}/s",
})
BT_UPLOAD_FIELD = FieldSpec("upload", FluentIcon.SHARE, {
    TaskStatus.RUNNING: toUploadText,
    TaskStatus.COMPLETED: lambda t, s, r: toUploadText(t, s, r) if t.isSeeding else None,
})


def toPeerText(task: BTTask, _speed: int, _received: int) -> str:
    return QCoreApplication.translate("TaskCard", "{0}/{1} Peers").format(
        task.peerCount, task.totalPeerCount
    )


BT_PEERS_FIELD = FieldSpec("peers", FluentIcon.INFO, {
    TaskStatus.RUNNING: toPeerText,
    TaskStatus.COMPLETED: lambda t, s, r: toPeerText(t, s, r) if t.isSeeding else None,
})

BT_STATE_LABELS = {
    "checking_files":       N("BTTaskCard", "校验已有文件"),
    "checking_resume_data": N("BTTaskCard", "检查续传状态"),
    "downloading_metadata": N("BTTaskCard", "获取元数据"),
    "downloading":          N("BTTaskCard", "下载中"),
    "finished":             N("BTTaskCard", "下载完成"),
    "seeding":              N("BTTaskCard", "做种中"),
    "allocating":           N("BTTaskCard", "分配文件中"),
    "queued_for_checking":  N("BTTaskCard", "等待校验"),
    "paused_downloading":   N("BTTaskCard", "已暂停下载"),
}

SILENT_STATES = frozenset({
    "downloading", "seeding", "checking_resume_data", "checking_files",
    "downloading_metadata", "allocating", "queued_for_checking", "finished",
})


class BTDraftCard(MultiFileDraftCard):
    fileSelectDialog = TorrentFileSelectDialog

    @property
    def task(self) -> BTTask:
        return self._task

    def _initWidget(self):
        super()._initWidget()
        icon = QFileIconProvider.IconType.File if self.task.isSingleFile else QFileIconProvider.IconType.Folder
        self.iconLabel.setImage(QFileIconProvider().icon(icon).pixmap(16, 16))
        self.iconLabel.setFixedSize(16, 16)


class BTTaskCard(MultiFileTaskCard):
    uploadLabel: IconBodyLabel
    fileSelectDialog = TorrentFileSelectDialog
    infoFields = [
        BT_SPEED_FIELD, BT_UPLOAD_FIELD, ETA_FIELD, SIZE_FIELD,
        BT_PEERS_FIELD,
    ]

    def _refreshForStatus(self, task):
        super()._refreshForStatus(task)
        if task.isSeeding and not self._isFileMissing:
            parts = []
            if task.shareRatioPercent > 0:
                parts.append(self.tr("分享率 {0}").format(f"{task.shareRatioPercent:.1f}%"))
            if task.seedingTimeSeconds > 0:
                parts.append(self.tr("做种 {0}").format(toReadableTime(task.seedingTimeSeconds)))
            self._setStatus(self.tr("做种中") + "  " + " · ".join(parts))
        elif task.status == TaskStatus.RUNNING and task.stateText and task.stateText != "downloading":
            self.progressBar.hide()
            label = BT_STATE_LABELS.get(task.stateText)
            if label:
                self._setStatus(self.tr(label))
        elif task.status != TaskStatus.RUNNING:
            parts = []
            if task.stateText and task.stateText not in SILENT_STATES:
                label = BT_STATE_LABELS.get(task.stateText)
                if label:
                    parts.append(self.tr(label))
            if task.shareRatioPercent > 0:
                parts.append(self.tr("分享率 {0}").format(f"{task.shareRatioPercent:.1f}%"))
            if task.seedingTimeSeconds > 0:
                parts.append(self.tr("做种 {0}").format(toReadableTime(task.seedingTimeSeconds)))
            summary = " · ".join(parts)
            if summary and not self._isFileMissing:
                self.statusLabel.setText(summary)
