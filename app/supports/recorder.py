from pathlib import Path

import orjson
from PySide6.QtCore import QStandardPaths
from loguru import logger

from app.bases.models import Task


class TaskRecorder:

    def __init__(self):
        appLocalDataLocation = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        recordFile = Path(f"{appLocalDataLocation}/GhostDownloader/Memory.log")
        if not recordFile.exists():
            recordFile.parent.mkdir(parents=True, exist_ok=True)
            recordFile.touch()

        self.fileHandle = open(recordFile, "r+", encoding="utf-8")
        self.fileHandle.seek(0)
        self.memorizedTasks: dict[str, Task] = {}

    def load(self):
        self.memorizedTasks = self.read()

    def read(self) -> dict[str, Task]:
        tasks: dict[str, Task] = {}
        self.fileHandle.seek(0)
        for line in self.fileHandle:
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

    # 其实根本不用 Override, status 也能发生改变
    # def override(self, task: Task):
    #     if task.taskId not in self.memorizedTasks:
    #         raise ValueError(f"task {task.taskId} does not exist")
    #     self.memorizedTasks[task.taskId] = task
    #     self.flush()

    def flush(self):
        self.fileHandle.seek(0)
        self.fileHandle.truncate()
        for task in self.memorizedTasks.values():
            try:
                self.fileHandle.write(task.serialize().decode("utf-8") + "\n")
            except Exception as e:
                logger.opt(exception=e).error("failed to write task {}", task.taskId)
        self.fileHandle.flush()

    def __del__(self):
        self.flush()
        self.fileHandle.close()

taskRecorder = TaskRecorder()
