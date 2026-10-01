from PySide6.QtCore import QCoreApplication
from qfluentwidgets import FluentIcon

from app.format import toReadableSize, toReadableTime
from app.models.task import TaskStatus
from app.view.cards.task_cards import ETA_FIELD, SIZE_FIELD, SPEED_FIELD, FieldSpec, TaskCard
from .task import ED2kTask


def toPeerText(task: ED2kTask, _speed: int, _received: int) -> str | None:
    if task.activePeerCount is None:
        return None
    total = max(task.activePeerCount, task.totalPeerCount)
    return QCoreApplication.translate("TaskCard", "{0}/{1} Peers").format(
        task.activePeerCount, total
    )


def toUploadText(task: ED2kTask, _speed: int, _received: int) -> str:
    return f"{toReadableSize(task.uploadRate)}/s"


ED2K_UPLOAD_FIELD = FieldSpec("upload", FluentIcon.SHARE, {
    TaskStatus.RUNNING: toUploadText,
    TaskStatus.COMPLETED: lambda t, s, r: toUploadText(t, s, r) if t.isSeeding else None,
})
ED2K_PEERS_FIELD = FieldSpec("peers", FluentIcon.INFO, {
    TaskStatus.RUNNING: toPeerText,
    TaskStatus.COMPLETED: lambda t, s, r: toPeerText(t, s, r) if t.isSeeding else None,
})


class ED2kTaskCard(TaskCard):
    infoFields = [
        SPEED_FIELD, ED2K_UPLOAD_FIELD, ETA_FIELD, SIZE_FIELD,
        ED2K_PEERS_FIELD,
    ]

    def _refreshForStatus(self, task: ED2kTask):
        super()._refreshForStatus(task)
        if task.isSeeding and not self._isFileMissing:
            self._setStatus(self.tr("，").join([self.tr("做种中"), *self._toSeedingParts(task)]))
        elif task.status != TaskStatus.RUNNING:
            parts = self._toSeedingParts(task)
            if parts and not self._isFileMissing:
                self.statusLabel.setText(self.tr("，").join(parts))

    def _toSeedingParts(self, task: ED2kTask) -> list[str]:
        parts = []
        if task.shareRatioPercent > 0:
            parts.append(self.tr("分享率 {0}").format(f"{task.shareRatioPercent:.1f}%"))
        if task.seedingTimeSeconds > 0:
            parts.append(self.tr("已做种 {0}").format(toReadableTime(task.seedingTimeSeconds)))
        return parts
