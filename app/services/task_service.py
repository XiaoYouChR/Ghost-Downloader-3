from pathlib import Path

import orjson
from PySide6.QtCore import QObject, QTimer, Signal, Slot
from loguru import logger

from app.bases.models import Task
from app.services.category_service import categoryService
from app.supports.config import cfg
from app.supports.paths import APP_DATA_DIR
from app.supports.utils import deduplicateFilename


class TaskService(QObject):

    taskAdded = Signal(object)
    taskRemoved = Signal(str)

    # Queued internal trigger: cross-thread emit hops to GUI event loop,
    # so scheduleFlush() is safe from any thread without a mutex.
    _flushRequested = Signal()

    def __init__(self):
        super().__init__()
        self.recordFile = Path(APP_DATA_DIR) / "Memory.log"
        if not self.recordFile.exists():
            self.recordFile.parent.mkdir(parents=True, exist_ok=True)
            self.recordFile.touch()

        self.tasks: dict[str, Task] = {}
        self._loaded = False

        self._flushTimer = QTimer(self)
        self._flushTimer.setSingleShot(True)
        self._flushTimer.setInterval(200)
        self._flushTimer.timeout.connect(self._flush)

        self._flushRequested.connect(self._onFlushRequested)

    def load(self):
        self.tasks = self._readAll()
        self._loaded = True

    def _readAll(self) -> dict[str, Task]:
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

    def add(self, task: Task):
        if task.taskId in self.tasks:
            raise ValueError(f"task {task.taskId} already exists")
        self.tasks[task.taskId] = task
        self.scheduleFlush()
        self.taskAdded.emit(task)

    def addTask(self, task: Task) -> None:
        if (
            cfg.enableCategory.value
            and task.category
            and task.path == Path(cfg.downloadFolder.value)
        ):
            folder = categoryService.folderOf(task.category)
            if folder:
                task.applySettings({"path": Path(folder)})

        originalTitle = task.title
        if deduplicateFilename(task):
            logger.info("检测到重名文件，已自动重命名 {} -> {}", originalTitle, task.title)

        self.add(task)

    def remove(self, task: Task):
        if task.taskId not in self.tasks:
            return
        taskId = task.taskId
        del self.tasks[taskId]
        self.scheduleFlush()
        self.taskRemoved.emit(taskId)

    def scheduleFlush(self):
        """Coalesce bursts via 200ms debounce. Safe from any thread."""
        self._flushRequested.emit()

    def flushNow(self):
        """Force synchronous flush. Use only at shutdown."""
        if self._flushTimer.isActive():
            self._flushTimer.stop()
        self._flush()

    @Slot()
    def _onFlushRequested(self):
        self._flushTimer.start()

    @Slot()
    def _flush(self):
        if not self._loaded:
            logger.warning("skip flush because task service has not been loaded")
            return

        lines: list[str] = []
        for task in self.tasks.values():
            try:
                lines.append(task.serialize().decode("utf-8") + "\n")
            except Exception as e:
                logger.opt(exception=e).error("failed to serialize task {}", task.taskId)

        tempFile = self.recordFile.with_name(self.recordFile.name + ".tmp")
        try:
            with open(tempFile, "w", encoding="utf-8") as f:
                f.writelines(lines)
            tempFile.replace(self.recordFile)
        except Exception as e:
            logger.opt(exception=e).error("failed to write task record file")


taskService = TaskService()
