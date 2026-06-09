from app.gui.task_list import TaskItem, TaskList
from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event


class Backend:
    """gui 调它来支使后台，并把后台发来的 event 落到界面模型上。"""

    def __init__(self, link: MemoryLink, taskList: TaskList) -> None:
        self._link = link
        self._taskList = taskList

    def addTask(self, url: str) -> None:
        self._link.toEngine(Command("addTask", {"url": url}))

    def receive(self, event: Event) -> None:
        if event.name == "taskAdded":
            self._taskList.add(TaskItem(event.data["task"]))
