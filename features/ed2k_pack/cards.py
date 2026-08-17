from PySide6.QtCore import QCoreApplication
from qfluentwidgets import FluentIcon

from app.models.task import TaskStatus
from app.view.cards.task_cards import FieldSpec, TaskCard
from .task import ED2kTask


def toPeerText(task: ED2kTask, _speed: int, _received: int) -> str | None:
    if task.activePeerCount is None:
        return None
    total = max(task.activePeerCount, task.totalPeerCount)
    return QCoreApplication.translate("TaskCard", "{0}/{1} Peers").format(
        task.activePeerCount, total
    )


ED2K_PEERS_FIELD = FieldSpec(
    "peers", FluentIcon.INFO, {TaskStatus.RUNNING: toPeerText}
)


class ED2kTaskCard(TaskCard):
    infoFields = [*TaskCard.infoFields, ED2K_PEERS_FIELD]
