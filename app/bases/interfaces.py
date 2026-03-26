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


class FeaturePack:
    priority: int = 0
    taskType: type["Task"] | tuple[type["Task"], ...] | None = None
    config: "PackConfig | None" = None

    def canHandle(self, url: str) -> bool:
        return False

    async def parse(self, payload: dict) -> "Task":
        raise NotImplementedError

    async def createTaskFromPayload(self, payload: dict) -> "Task | None":
        return None

    def canHandleTask(self, task: "Task") -> bool:
        if self.taskType is not None and isinstance(task, self.taskType):
            return True

        taskUrl = getattr(task, "url", None)
        if isinstance(taskUrl, str):
            return self.canHandle(taskUrl)

        return False

    def createTaskCard(self, task: "Task", parent=None) -> "TaskCard | None":
        return None

    def createResultCard(self, task: "Task", parent=None) -> "ResultCard | None":
        return None

    def load(self, mainWindow: "MainWindow"):
        pass
