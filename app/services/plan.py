from __future__ import annotations

from enum import IntEnum
from typing import Callable


class PlanAction(IntEnum):
    SHUTDOWN = 0
    RESTART = 1
    SLEEP = 2
    OPEN_FILE = 3


class Plan:

    def __init__(self, allCompleted: Callable[[], bool]) -> None:
        self._allCompleted = allCompleted
        self.action: PlanAction | None = None
        self.filePath: str = ""
        self._onCleared: Callable | None = None

    def set(self, action: PlanAction, filePath: str = "",
            onCleared: Callable | None = None) -> None:
        self.action = action
        self.filePath = filePath
        self._onCleared = onCleared

    def clear(self) -> None:
        callback = self._onCleared
        self.action = None
        self.filePath = ""
        self._onCleared = None
        if callback:
            callback()

    def trigger(self) -> None:
        if self.action is None:
            return
        if not self._allCompleted():
            return

        from app.platform.desktop import openFile, restart, shutdown, sleep

        action, filePath = self.action, self.filePath
        self.clear()

        if action == PlanAction.OPEN_FILE:
            if filePath:
                openFile(filePath)
        elif action == PlanAction.RESTART:
            restart()
        elif action == PlanAction.SLEEP:
            sleep()
        else:
            shutdown()
