# pyright: reportUnannotatedClassAttribute=false, reportAny=false, reportMissingParameterType=false, reportUnusedCallResult=false

from pathlib import Path
from typing import cast

import orjson
from PySide6.QtCore import QStandardPaths
from loguru import logger

from app.bases.models import Task
from app.feature_pack.api import Task as V1Task
from app.feature_pack.internal.recorder import TaskRecorder as V1TaskRecorder


class TaskRecorder:

    def __init__(self):
        appLocalDataLocation = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
        self.recordFile = Path(f"{appLocalDataLocation}/GhostDownloader/Memory.log")
        if not self.recordFile.exists():
            self.recordFile.parent.mkdir(parents=True, exist_ok=True)
            self.recordFile.touch()

        self.memorizedTasks: dict[str, Task] = {}
        self._loaded = False

    def load(self):
        self.memorizedTasks = self.read()
        self._loaded = True

    def read(self) -> dict[str, Task]:
        tasks: dict[str, Task] = {}
        with open(self.recordFile, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = orjson.loads(line)
                task = Task.deserialize(obj)
                tasks[task.taskId] = task
            except Exception as e:
                logger.opt(exception=e).error("failed to parse task record")
        return tasks

    def add(self, task: Task, flush=True):
        if task.taskId in self.memorizedTasks:
            raise ValueError(f"task {task.taskId} already exists")
        self.memorizedTasks[task.taskId] = task
        if flush:
            self.flush()

    def remove(self, task: Task, flush=True):
        if task.taskId not in self.memorizedTasks:
            return

        del self.memorizedTasks[task.taskId]
        if flush:
            self.flush()

    def flush(self):
        if not self._loaded:
            logger.warning("skip flush because task recorder has not been loaded")
            return

        lines: list[str] = []
        for task in self.memorizedTasks.values():
            try:
                lines.append(task.serialize().decode("utf-8") + "\n")
            except Exception as e:
                logger.opt(exception=e).error("failed to write task {}", task.taskId)

        tempFile = self.recordFile.with_name(self.recordFile.name + ".tmp")
        with open(tempFile, "w", encoding="utf-8") as f:
            f.writelines(lines)

        tempFile.replace(self.recordFile)


class HostTaskRecorder:
    """Route legacy tasks and V1 Feature Pack tasks to their own recorders."""

    def __init__(self) -> None:
        self.legacyRecorder = TaskRecorder()
        self.featurePackRecorder = V1TaskRecorder()

    @property
    def memorizedTasks(self) -> dict[str, object]:
        tasks: dict[str, object] = dict(self.legacyRecorder.memorizedTasks)
        tasks.update(self.featurePackRecorder.memorizedTasks)
        return tasks

    def load(self) -> None:
        self.legacyRecorder.load()
        self.featurePackRecorder.load()

    def read(self) -> dict[str, object]:
        tasks: dict[str, object] = dict(self.legacyRecorder.read())
        tasks.update(self.featurePackRecorder.read())
        return tasks

    def add(self, task: object, flush: bool = True) -> None:
        if isinstance(task, V1Task):
            self.featurePackRecorder.add(task, flush)
            return

        self.legacyRecorder.add(cast(Task, task), flush)

    def remove(self, task: object, flush: bool = True) -> None:
        if isinstance(task, V1Task):
            self.featurePackRecorder.remove(task, flush)
            return

        self.legacyRecorder.remove(cast(Task, task), flush)

    def flush(self) -> None:
        self.legacyRecorder.flush()
        self.featurePackRecorder.flush()


taskRecorder = HostTaskRecorder()
