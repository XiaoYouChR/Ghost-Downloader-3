from pathlib import Path

import orjson
from PySide6.QtCore import QStandardPaths
from loguru import logger

from app.bases.models import Task


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

taskRecorder = TaskRecorder()
