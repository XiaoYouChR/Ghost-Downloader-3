import time

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor
from qfluentwidgets import FluentIcon

from app.format import toReadableSize, toReadableTime
from app.models.task import TaskStatus
from app.view.cards.task_cards import ETA_FIELD, SIZE_FIELD, SPEED_FIELD, FieldSpec, TaskCard
from .kelpie import Progress
from .session import ed2kSession, toHeldMinutes
from .task import ED2kTask


def toWaitText(minutes: int) -> str:
    if minutes == 0:
        return QCoreApplication.translate("ED2kTaskCard", "不到 1 分钟")
    return QCoreApplication.translate("ED2kTaskCard", "约 {0} 分钟").format(minutes)


def toHeldText(progress: Progress | None, now: int) -> str | None:
    minutes = toHeldMinutes(progress, now)
    if minutes is None:
        return None
    return QCoreApplication.translate(
        "ED2kTaskCard", "为免被对方判为请求过频而封禁，{0} 个来源{1}后再请求",
    ).format(progress.heldSources, toWaitText(minutes))


def toShortHeldText(progress: Progress | None, now: int) -> str | None:
    minutes = toHeldMinutes(progress, now)
    if minutes is None:
        return None
    return QCoreApplication.translate("ED2kTaskCard", "{0} 个来源{1}后恢复").format(
        progress.heldSources, toWaitText(minutes))


def toPeerText(task: ED2kTask, _speed: int, _received: int) -> str | None:
    progress = ed2kSession.progressOf(task)
    if progress is None:
        return None
    return QCoreApplication.translate("ED2kTaskCard", "{0}/{1} 来源").format(progress.activePeers, progress.peers)


def toUploadText(task: ED2kTask, _speed: int, _received: int) -> str:
    progress = ed2kSession.progressOf(task)
    return f"{toReadableSize(progress.uploadRate if progress is not None else 0)}/s"


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
        if self._isFileMissing:
            return
        progress, now = ed2kSession.progressOf(task), int(time.time() * 1000)
        shortHeldText = toShortHeldText(progress, now)
        if task.status == TaskStatus.RUNNING and shortHeldText is not None:
            self._setStatus(shortHeldText)
            self.statusLabel.setTextColor(QColor(200, 160, 80), QColor(200, 170, 100))
            return
        parts = self._toSeedingParts(task)
        if task.isSeeding:
            self._setStatus(self.tr("，").join([self.tr("做种中"), *parts]))
        elif task.status != TaskStatus.RUNNING and parts:
            self.statusLabel.setText(self.tr("，").join(parts))

    def _toSeedingParts(self, task: ED2kTask) -> list[str]:
        parts = []
        if task.shareRatioPercent > 0:
            parts.append(self.tr("分享率 {0}").format(f"{task.shareRatioPercent:.1f}%"))
        if task.seedingTimeSeconds > 0:
            parts.append(self.tr("已做种 {0}").format(toReadableTime(task.seedingTimeSeconds)))
        return parts
