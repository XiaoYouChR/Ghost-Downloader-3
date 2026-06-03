from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

from app.bases.models import TaskStage

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow
    from app.view.components.cards import TaskCard
    from app.view.components.cards import ResultCard
    from app.bases.models import Task, PackConfig


@dataclass(frozen=True)
class FileType:
    extensions: tuple[str, ...]
    displayName: str
    mimeType: str
    icon: str


class Worker:
    def __init__(self, stage: TaskStage):
        self.stage = stage

    async def run(self):
        raise NotImplementedError


class FeaturePack:
    packId: str = ""
    priority: int = 0
    config: "PackConfig | None" = None

    def matches(self, url: str) -> bool:
        return False

    async def parse(self, payload: dict) -> "Task":
        raise NotImplementedError

    def taskCard(self, task: "Task", parent=None) -> "TaskCard":
        from app.view.components.cards import UniversalTaskCard
        return UniversalTaskCard(task, parent)

    def resultCard(self, task: "Task", parent=None) -> "ResultCard":
        from app.view.components.cards import UniversalResultCard
        return UniversalResultCard(task, parent)

    def fileTypes(self) -> list[FileType]:
        return []

    def setup(self, mainWindow: "MainWindow"):
        pass

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)
