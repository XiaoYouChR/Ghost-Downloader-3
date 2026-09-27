from __future__ import annotations

import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.task_service import NameConflictChoice
from app.signal import Signal

if TYPE_CHECKING:
    from app.models.task import Task


@dataclass(frozen=True)
class NameConflict:
    task: Task
    takenPath: Path
    isFolder: bool
    existingSize: int
    modifiedAt: int
    restCount: int


class NameConflictQueue:
    conflictChanged = Signal(object)

    def __init__(self, probeConflict: Callable[[Task], Path | None], add: Callable[..., bool],
                 post: Callable[..., None]):
        self._probeConflict = probeConflict
        self._add = add
        self._post = post
        self._tasks: list[Task] = []
        self._conflict: NameConflict | None = None
        self._isRefreshPosted = False

    def add(self, task: Task) -> None:
        self._tasks.append(task)
        if self._conflict is None and not self._isRefreshPosted:
            self._isRefreshPosted = True
            self._post(self._refresh)

    def setChoice(self, taskId: str, choice: NameConflictChoice, isAppliedToRest: bool) -> None:
        conflict = self._conflict
        if conflict is None or conflict.task.taskId != taskId:
            return
        self._add(conflict.task, choice=choice)
        if isAppliedToRest:
            rest, self._tasks = self._tasks[:conflict.restCount], self._tasks[conflict.restCount:]
            for task in rest:
                self._add(task, choice=choice)
        self._refresh()

    def cancel(self, taskId: str) -> None:
        if self._conflict is None or self._conflict.task.taskId != taskId:
            return
        self._refresh()

    def _refresh(self) -> None:
        self._isRefreshPosted = False
        self._conflict = None
        while self._tasks:
            task = self._tasks.pop(0)
            takenPath = self._probeConflict(task)
            if takenPath is None:
                self._add(task, choice=NameConflictChoice.KEEP_BOTH)
                continue
            info = takenPath.stat()
            self._conflict = NameConflict(task, takenPath, stat.S_ISDIR(info.st_mode), info.st_size,
                                          int(info.st_mtime), len(self._tasks))
            break
        self.conflictChanged.emit(self._conflict)
