from types import SimpleNamespace

import pytest

from app.engine.engine import Engine
from app.gui.backend import Backend
from app.gui.task_list import TaskList
from app.protocol.link import MemoryLink


@pytest.fixture
def spine(qapp):
    # 接好一条 gui↔engine：link 连两端，gui attach 后即可收发。
    link = MemoryLink()
    engine = Engine(link)
    taskList = TaskList()
    backend = Backend(link, taskList)
    link.connect(engine.receive, backend.receive)
    backend.attach()
    return SimpleNamespace(link=link, engine=engine, backend=backend, taskList=taskList)
