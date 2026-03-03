from typing import TYPE_CHECKING

from app.bases.models import TaskStage

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow
    from app.view.components.cards import TaskCard



class Worker:
    def __init__(self, stage: TaskStage):
        pass


class FeaturePack:

    async def parse(self, payload: dict) -> "TaskCard":
        raise NotImplementedError

    def load(self, mainWindow: "MainWindow"):
        pass
