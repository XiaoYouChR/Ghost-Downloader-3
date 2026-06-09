from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from app.bases.models import Task
from app.engine.engine import Engine
from app.gui.backend import Backend
from app.gui.task_list import TaskList
from app.protocol.link import MemoryLink


def _fakeParse(url: str) -> Task:
    # 测试用：不走网络，直接从 URL 建 Task（替掉真 http 探测）。
    title = urlparse(url).path.rsplit("/", 1)[-1] or url
    return Task(title=title, url=url, packId="http")


def _runNow(parsed, callback) -> None:
    # 测试用：同步立即回调，替掉 coreService 的异步调度。
    callback(parsed, None)


@pytest.fixture
def spine(qapp):
    # 接好一条 gui↔engine：link 连两端，gui attach 后即可收发；parse/run 注入离线 fake。
    link = MemoryLink()
    engine = Engine(link, parse=_fakeParse, run=_runNow)
    taskList = TaskList()
    backend = Backend(link, taskList)
    link.connect(engine.receive, backend.receive)
    backend.attach()
    return SimpleNamespace(link=link, engine=engine, backend=backend, taskList=taskList)
