from typing import TYPE_CHECKING

from app.bases.models import TaskStage

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow
    from app.view.components.cards import TaskCard
    from app.bases.models import Task


class Worker:
    def __init__(self, stage: TaskStage):
        pass


class FeaturePack:
    priority: int

    def canHandle(self, url) -> bool:
        raise NotImplementedError

    async def parse(self, payload: dict) -> "Task":
        raise NotImplementedError

    def load(self, mainWindow: "MainWindow"):
        pass
