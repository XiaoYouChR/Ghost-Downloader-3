from urllib.parse import urlparse
from uuid import uuid4

from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event


class Engine:
    """后台本体：收 command、加任务、回发 event。tracer 阶段先用最小任务记录，
    之后接 taskService / featureService。"""

    def __init__(self, link: MemoryLink) -> None:
        self._link = link
        self._tasks: dict[str, dict] = {}

    def receive(self, command: Command) -> None:
        if command.name == "addTask":
            self._addTask(command.data["url"])

    def _addTask(self, url: str) -> None:
        task = {
            "taskId": f"tsk_{uuid4().hex}",
            "title": urlparse(url).path.rsplit("/", 1)[-1] or url,
            "url": url,
        }
        self._tasks[task["taskId"]] = task
        self._link.toGui(Event("taskAdded", {"task": task}))
