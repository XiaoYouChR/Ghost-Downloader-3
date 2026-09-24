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
            parts = []
            if task.seedingTimeSeconds > 0:
                parts.append(self.tr("已共享 {0}").format(
                    toReadableTime(task.seedingTimeSeconds)))
            self._setStatus(self.tr("共享中") + ("  " + " · ".join(parts) if parts else ""))
        elif task.status != TaskStatus.RUNNING and task.seedingTimeSeconds > 0:
            self.statusLabel.setText(
                self.statusLabel.text() + " · " + self.tr("已共享 {0}").format(
                    toReadableTime(task.seedingTimeSeconds))
            )
