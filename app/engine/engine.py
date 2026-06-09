from urllib.parse import urlparse
from uuid import uuid4

from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event


class Engine:
    """后台本体：收 command、加任务、回发 event。没有 gui attach 时不发事件（省内存）。
    tracer 阶段先用最小任务记录，之后接 taskService / featureService。"""

    def __init__(self, link: MemoryLink) -> None:
        self._link = link
        self._tasks: dict[str, dict] = {}
        self._attached = False

    def receive(self, command: Command) -> None:
        if command.name == "attach":
            self._attach()
        elif command.name == "detach":
            self._attached = False
        elif command.name == "addTask":
            self._addTask(command.data["url"])
        elif command.name == "pause":
            self._pause(command.data["taskId"])
        elif command.name == "remove":
            self._remove(command.data["taskId"])

    def _attach(self) -> None:
        self._attached = True
        self._emit(Event("snapshot", {"tasks": list(self._tasks.values())}))

    def _addTask(self, url: str) -> None:
        task = {
            "taskId": f"tsk_{uuid4().hex}",
            "title": urlparse(url).path.rsplit("/", 1)[-1] or url,
            "url": url,
            "status": "waiting",
        }
        self._tasks[task["taskId"]] = task
        self._emit(Event("taskAdded", {"task": task}))

    def _pause(self, taskId: str) -> None:
        task = self._tasks[taskId]
        task["status"] = "paused"
        self._emit(Event("taskChanged", {"task": task}))

    def _remove(self, taskId: str) -> None:
        del self._tasks[taskId]
        self._emit(Event("taskRemoved", {"taskId": taskId}))

    def _emit(self, event: Event) -> None:
        # 没有 gui 在听就不发：gui 被杀后 engine 不白费力气算/发，省 CPU 与内存
        if self._attached:
            self._link.toGui(event)
