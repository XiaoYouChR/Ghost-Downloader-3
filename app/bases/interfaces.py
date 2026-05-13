from typing import TYPE_CHECKING

from app.bases.models import TaskStage

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow
    from app.view.components.cards import TaskCard
    from app.view.components.cards import ResultCard
    from app.bases.models import Task, PackConfig


class Worker:
    def __init__(self, stage: TaskStage):
        self.stage = stage

    async def run(self):
        raise NotImplementedError


class FeaturePack:
    packId: str
    priority: int = 0
    config: "PackConfig | None" = None

    def matches(self, url: str) -> bool:
        return False

    async def parse(self, payload: dict) -> "Task":
        raise NotImplementedError

    def taskCard(self, task: "Task", parent=None) -> "TaskCard | None":
        from app.view.components.cards import UniversalTaskCard
        return UniversalTaskCard(task, parent)

    def resultCard(self, task: "Task", parent=None) -> "ResultCard | None":
        from app.view.components.cards import UniversalResultCard
        return UniversalResultCard(task, parent)

    def setup(self, mainWindow: "MainWindow"):
        pass
