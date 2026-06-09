from PySide6.QtCore import QObject, Slot

from app.gui.task_list import TaskItem, TaskList
from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event


class Backend(QObject):
    """gui 调它来支使后台，并把后台发来的 event 落到界面模型上。QML 经 @Slot 调用。"""

    def __init__(self, link: MemoryLink, taskList: TaskList) -> None:
        super().__init__()
        self._link = link
        self._taskList = taskList

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
    def remove(self, taskId: str) -> None:
        self._link.toEngine(Command("remove", {"taskId": taskId}))

    def receive(self, event: Event) -> None:
        if event.name == "snapshot":
            self._taskList.reset(event.data["tasks"])
        elif event.name == "taskAdded":
            self._taskList.add(TaskItem(event.data["task"]))
        elif event.name == "taskChanged":
            self._taskList.update(event.data["task"])
        elif event.name == "taskRemoved":
            self._taskList.remove(event.data["taskId"])
