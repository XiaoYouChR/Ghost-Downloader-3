from typing import TYPE_CHECKING

from app.view.components.cards import TaskCardBase

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow


class FeaturePackBase:

    def parse(self, payload: dict) -> TaskCardBase:
        raise NotImplementedError

    def load(self, mainWindow: "MainWindow"):
        raise NotImplementedError