from app.bases.models import Task, TaskStatus
from app.engine.config import Config
from app.engine.engine import Engine
from app.engine.settings import GLOBAL_SETTINGS
from app.gui.backend import Backend
from app.gui.task_list import TaskList
from app.protocol.link import MemoryLink
from fakes import FakeDownloads, FakeStore


def _wire(store: FakeStore):
    link = MemoryLink()
    engine = Engine(link, FakeDownloads(), store, Config(GLOBAL_SETTINGS))
    taskList = TaskList()
    backend = Backend(link, taskList)
    link.connect(engine.receive, backend.receive)
    backend.attach()
    return backend, taskList


def test_persistedTasks_appearOnAttach(qapp):
    # 重启场景：store 里已有任务，engine 启动加载，attach 后 gui 看到。
    saved = Task(title="old.bin", url="https://example.com/old.bin", packId="http")
    _, taskList = _wire(FakeStore([saved]))

    assert taskList.rowCount() == 1
    assert taskList.data(taskList.index(0, 0), TaskList.TitleRole) == "old.bin"


def test_loadedRunningTask_shownPaused(qapp):
    # 加载时未完成任务并未真在跑，显示为暂停。
    saved = Task(title="x.bin", url="https://example.com/x.bin", packId="http")
    saved.setStatus(TaskStatus.RUNNING)
    _, taskList = _wire(FakeStore([saved]))

    assert taskList.data(taskList.index(0, 0), TaskList.StatusRole) == "PAUSED"


def test_addTask_persists(spine):
    spine.backend.addTask("https://example.com/movie.mp4")

    assert len(spine.store.added) == 1


def test_remove_persists(spine):
    spine.backend.addTask("https://example.com/movie.mp4")
    taskId = spine.taskList.data(spine.taskList.index(0, 0), TaskList.IdRole)

    spine.backend.remove(taskId)

    assert len(spine.store.removed) == 1
