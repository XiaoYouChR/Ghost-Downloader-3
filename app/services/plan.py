from enum import IntEnum


class PlanAction(IntEnum):
    SHUTDOWN = 0
    RESTART = 1
    OPEN_FILE = 2


class Plan:

    def __init__(self):
        self.action: PlanAction | None = None
        self.filePath: str = ""
        self._onCleared = None

    def set(self, action: PlanAction, filePath: str = "", onCleared=None) -> None:
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
        from app.models.task import TaskStatus
        from app.services.task_service import taskService
        if any(t.status != TaskStatus.COMPLETED for t in taskService.tasks):
            return

        from app.platform.desktop import openFile, restart, shutdown

        action, filePath = self.action, self.filePath
        self.clear()

        if action == PlanAction.OPEN_FILE:
            if filePath:
                openFile(filePath)
        elif action == PlanAction.RESTART:
            restart()
        else:
            shutdown()


plan = Plan()
