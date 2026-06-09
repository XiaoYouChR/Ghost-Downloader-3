from urllib.parse import urlparse

from orjson import loads

from app.bases.models import Task, TaskStatus
from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event


class Engine:
    """后台本体：收 command、加任务、回发 event。没有 gui attach 时不发事件（省内存）。
    持真 Task；事件回传 task.serialize() 的线缆字段（socket 上也是这一份）。"""

    def __init__(self, link: MemoryLink) -> None:
        self._link = link
        self._tasks: dict[str, Task] = {}
        self._attached = False

    def receive(self, command: Command) -> None:
        if command.name == "attach":
            self._attach()
        elif command.name == "detach":
            self._attached = False
        elif command.name == "addTask":
            self._addTask(command.data["url"])
        elif command.name == "pause":
            self._setStatus(self._tasks[command.data["taskId"]], TaskStatus.PAUSED)
        elif command.name == "resume":
            self._setStatus(self._tasks[command.data["taskId"]], TaskStatus.RUNNING)
        elif command.name == "pauseAll":
            self._setAll(TaskStatus.PAUSED)
        elif command.name == "startAll":
            self._setAll(TaskStatus.RUNNING)
        elif command.name == "remove":
            self._remove(command.data["taskId"])

    def _attach(self) -> None:
        self._attached = True
        self._emit(Event("snapshot", {"tasks": [self._toWire(task) for task in self._tasks.values()]}))

    def _addTask(self, url: str) -> None:
        title = urlparse(url).path.rsplit("/", 1)[-1] or url
        task = Task(title=title, url=url, packId="http")
        self._tasks[task.taskId] = task
        self._emit(Event("taskAdded", {"task": self._toWire(task)}))

    def _setStatus(self, task: Task, status: TaskStatus) -> None:
        task.setStatus(status)
        self._emit(Event("taskChanged", {"task": self._toWire(task)}))

    def _setAll(self, status: TaskStatus) -> None:
        for task in self._tasks.values():
            self._setStatus(task, status)

    def _remove(self, taskId: str) -> None:
        del self._tasks[taskId]
        self._emit(Event("taskRemoved", {"taskId": taskId}))

    def _toWire(self, task: Task) -> dict:
        # engine→gui 的线缆格式：序列化后的 Task 字段（跨进程时 socket 上也是这一份）
        return loads(task.serialize())

    def _emit(self, event: Event) -> None:
        # 没有 gui 在听就不发：gui 被杀后 engine 不白费力气算/发，省 CPU 与内存
        if self._attached:
            self._link.toGui(event)
