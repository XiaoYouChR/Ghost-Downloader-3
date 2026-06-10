from PySide6.QtCore import Property, QObject, Signal, Slot

from app.gui.file_selection import FileSelection
from app.gui.task_list import TaskItem, TaskList
from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event
from app.supports import utils


class Backend(QObject):
    """gui 调它来支使后台，并把后台发来的 event 落到界面模型上。QML 经 @Slot 调用。"""

    globalSpeedChanged = Signal()
    filesModelChanged = Signal()
    filesRequested = Signal()
    configChanged = Signal()
    hashReady = Signal()

    def __init__(self, link: MemoryLink, taskList: TaskList) -> None:
        super().__init__()
        self._link = link
        self._taskList = taskList
        self._globalSpeedText = ""
        self._filesModel: FileSelection | None = None
        self._editingTaskId = ""
        self._config: dict = {}
        self._hashText = ""

    def _hash(self) -> str:
        return self._hashText

    hashText = Property(str, _hash, notify=hashReady)

    @Slot(str)
    def verifyHash(self, taskId: str) -> None:
        self._hashText = ""
        self.hashReady.emit()
        self._link.toEngine(Command("verifyHash", {"taskId": taskId}))

    def _maxTaskNum(self) -> int:
        return self._config.get("maxTaskNum", 1)

    maxTaskNum = Property(int, _maxTaskNum, notify=configChanged)

    def _downloadFolder(self) -> str:
        return self._config.get("downloadFolder", "")

    downloadFolder = Property(str, _downloadFolder, notify=configChanged)

    @Slot(str, "QVariant")
    def setConfig(self, key: str, value) -> None:
        self._link.toEngine(Command("setConfig", {"key": key, "value": value}))

    def _globalSpeed(self) -> str:
        return self._globalSpeedText

    globalSpeedText = Property(str, _globalSpeed, notify=globalSpeedChanged)

    def _files(self) -> QObject | None:
        return self._filesModel

    filesModel = Property(QObject, _files, notify=filesModelChanged)

    @Slot(str)
    def editFiles(self, taskId: str) -> None:
        self._editingTaskId = taskId
        self._filesModel = FileSelection(self._taskList.filesOf(taskId))
        self.filesModelChanged.emit()
        self.filesRequested.emit()

    @Slot()
    def confirmFiles(self) -> None:
        if self._filesModel is None:
            return
        indexes = self._filesModel.selectedIndexes()
        self._link.toEngine(Command("setSelection", {"taskId": self._editingTaskId, "indexes": indexes}))

    @Slot()
    def attach(self) -> None:
        self._link.toEngine(Command("attach"))

    @Slot()
    def detach(self) -> None:
        self._link.toEngine(Command("detach"))

    @Slot(str)
    def addTask(self, url: str) -> None:
        self._link.toEngine(Command("addTask", {"url": url}))

    @Slot(str)
    def pause(self, taskId: str) -> None:
        self._link.toEngine(Command("pause", {"taskId": taskId}))

    @Slot(str)
    def resume(self, taskId: str) -> None:
        self._link.toEngine(Command("resume", {"taskId": taskId}))

    @Slot()
    def startAll(self) -> None:
        self._link.toEngine(Command("startAll"))

    @Slot()
    def pauseAll(self) -> None:
        self._link.toEngine(Command("pauseAll"))

    @Slot(str)
    def remove(self, taskId: str) -> None:
        self._link.toEngine(Command("remove", {"taskId": taskId}))

    @Slot()
    def removeSelected(self) -> None:
        for taskId in self._taskList.selectedIds():
            self._link.toEngine(Command("remove", {"taskId": taskId}))
        self._taskList.setSelectionMode(False)

    @Slot()
    def clearCompleted(self) -> None:
        self._link.toEngine(Command("clearCompleted"))

    @Slot(str, str)
    def rename(self, taskId: str, title: str) -> None:
        self._link.toEngine(Command("rename", {"taskId": taskId, "title": title}))

    @Slot(str)
    def openFile(self, path: str) -> None:
        # 打开下载好的文件是 gui 端的 OS 动作，不过缝
        utils.openFile(path)

    @Slot(str)
    def openFolder(self, path: str) -> None:
        utils.openFolder(path)

    def receive(self, event: Event) -> None:
        if event.name == "snapshot":
            self._taskList.reset(event.data["tasks"])
        elif event.name == "taskAdded":
            self._taskList.add(TaskItem(event.data["task"]))
        elif event.name == "taskChanged":
            self._taskList.update(event.data["task"])
        elif event.name == "taskRemoved":
            self._taskList.remove(event.data["taskId"])
        elif event.name == "stats":
            speed = event.data["globalSpeed"]
            self._globalSpeedText = f"{utils.toReadableSize(speed)}/s" if speed else ""
            self.globalSpeedChanged.emit()
        elif event.name == "config":
            self._config.update(event.data["values"])
            self.configChanged.emit()
        elif event.name == "hashResult":
            self._hashText = event.data["hash"]
            self.hashReady.emit()
