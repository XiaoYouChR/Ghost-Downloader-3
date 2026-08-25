from PySide6.QtCore import QCoreApplication
from qfluentwidgets import FluentIcon

from app.format import toReadableSize, toReadableTime
from app.models.task import TaskStatus
from app.view.cards.task_cards import FieldSpec, TaskCard, toSizeText
from .task import ED2kTask


def toPeerText(task: ED2kTask, _speed: int, _received: int) -> str | None:
    if task.activePeerCount is None:
        return None
    total = max(task.activePeerCount, task.totalPeerCount)
    return QCoreApplication.translate("TaskCard", "{0}/{1} Peers").format(
        task.activePeerCount, total
    )


ED2K_SPEED_FIELD = FieldSpec("speed", FluentIcon.SPEED_HIGH, {
    TaskStatus.RUNNING: lambda t, s, r: None if t.isSharing else f"{toReadableSize(s)}/s",
})
ED2K_UPLOAD_FIELD = FieldSpec("upload", FluentIcon.SHARE, {
    TaskStatus.RUNNING: lambda t, s, r: f"{toReadableSize(t.uploadRate)}/s",
})
ED2K_ETA_FIELD = FieldSpec("eta", FluentIcon.STOP_WATCH, {
    TaskStatus.RUNNING: lambda t, s, r: None if t.isSharing else (
        toReadableTime(int((t.fileSize - r) / s)) if t.fileSize > 0 and s > 0 else "--"
    ),
})
ED2K_SIZE_FIELD = FieldSpec("size", FluentIcon.LIBRARY, {
    None: lambda t, s, r: None if t.status == TaskStatus.RUNNING and t.isSharing else toSizeText(t, s, r),
})
ED2K_PEERS_FIELD = FieldSpec(
    "peers", FluentIcon.INFO, {TaskStatus.RUNNING: toPeerText}
)


class ED2kTaskCard(TaskCard):
    infoFields = [
        ED2K_SPEED_FIELD, ED2K_UPLOAD_FIELD, ED2K_ETA_FIELD, ED2K_SIZE_FIELD,
        ED2K_PEERS_FIELD,
    ]

    def _refreshForStatus(self, task: ED2kTask):
        super()._refreshForStatus(task)
        if task.status == TaskStatus.RUNNING and task.isSharing:
            self.progressBar.hide()
            parts = []
            if task.sharingTimeSeconds > 0:
                parts.append(self.tr("已共享 {0}").format(
                    toReadableTime(task.sharingTimeSeconds)))
            self._setStatus(self.tr("共享中") + ("  " + " · ".join(parts) if parts else ""))
        elif task.status != TaskStatus.RUNNING and task.sharingTimeSeconds > 0:
            self.statusLabel.setText(
                self.statusLabel.text() + " · " + self.tr("已共享 {0}").format(
                    toReadableTime(task.sharingTimeSeconds))
            )
