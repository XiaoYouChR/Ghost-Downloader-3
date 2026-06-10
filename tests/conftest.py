from types import SimpleNamespace

import pytest

from app.engine.config import Config
from app.engine.engine import Engine
from app.engine.settings import GLOBAL_SETTINGS
from app.gui.backend import Backend
from app.gui.task_list import TaskList
from app.protocol.link import MemoryLink
from fakes import FakeDownloads, FakeStore


@pytest.fixture
def spine(qapp):
    # 接好一条 gui↔engine：link 连两端，gui attach 后即可收发；下载/持久化/配置边界注入离线版（不碰真 cfg）。
    link = MemoryLink()
    downloads = FakeDownloads()
    store = FakeStore()
    config = Config(GLOBAL_SETTINGS)
    engine = Engine(link, downloads, store, config)
    taskList = TaskList()
    backend = Backend(link, taskList)
    link.connect(engine.receive, backend.receive)
    backend.attach()
    return SimpleNamespace(
        link=link, engine=engine, backend=backend, taskList=taskList,
        downloads=downloads, store=store, config=config,
    )
