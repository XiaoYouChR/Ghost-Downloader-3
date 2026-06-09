from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from app.bases.models import Task
from app.engine.engine import Engine
from app.gui.backend import Backend
from app.gui.task_list import TaskList
from app.protocol.link import MemoryLink


class FakeDownloads:
    """测试用下载边界：不走网络、不起线程，同步建 Task 并记录 start/stop。"""

    def __init__(self) -> None:
        self.started: list[Task] = []
        self.stopped: list[Task] = []

    def parse(self, url: str) -> Task:
        title = urlparse(url).path.rsplit("/", 1)[-1] or url
        return Task(title=title, url=url, packId="http")

    def run(self, parsed, callback) -> None:
        callback(parsed, None)

    def start(self, task: Task) -> None:
        self.started.append(task)

    def stop(self, task: Task) -> None:
        self.stopped.append(task)


@pytest.fixture
def spine(qapp):
    # 接好一条 gui↔engine：link 连两端，gui attach 后即可收发；下载边界注入离线 fake。
    link = MemoryLink()
    downloads = FakeDownloads()
    engine = Engine(link, downloads)
    taskList = TaskList()
    backend = Backend(link, taskList)
    link.connect(engine.receive, backend.receive)
    backend.attach()
    return SimpleNamespace(
        link=link, engine=engine, backend=backend, taskList=taskList, downloads=downloads
    )
