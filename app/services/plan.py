from __future__ import annotations

from enum import IntEnum

from app.signal import Signal


class PlanAction(IntEnum):
    SHUTDOWN = 0
    RESTART = 1
    SLEEP = 2
    OPEN_FILE = 3
    QUIT = 4


class Plan:
    changed = Signal()

    def __init__(self, allCompleted):
        self._allCompleted = allCompleted
        self.action: PlanAction | None = None
        self.filePath: str = ""

    def set(self, action: PlanAction, filePath: str = "") -> None:
        self.action = action
        self.filePath = filePath
        self.changed.emit()

    def clear(self) -> None:
        self.action = None
        self.filePath = ""
        self.changed.emit()

    def trigger(self) -> None:
        if self.action is None or not self._allCompleted():
            return

        from PySide6.QtWidgets import QApplication
        from app.platform.desktop import openFile, restart, shutdown, sleep

        action, filePath = self.action, self.filePath
        self.clear()

        if action == PlanAction.OPEN_FILE:
            if filePath:
                openFile(filePath)
        elif action == PlanAction.QUIT:
            QApplication.quit()
        elif action == PlanAction.RESTART:
            restart()
        elif action == PlanAction.SLEEP:
            sleep()
        else:
            shutdown()
