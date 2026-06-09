from app.gui.backend import Backend
from app.gui.task_list import TaskList


def test_addTask_appearsInGuiModel(spine):
    # 脊柱 tracer: gui 发 addTask → 过 link → engine 加任务、回发 taskAdded → 落进 TaskList。
    spine.backend.addTask("https://example.com/movie.mp4")

    assert spine.taskList.rowCount() == 1
    index = spine.taskList.index(0, 0)
    assert spine.taskList.data(index, TaskList.TitleRole) == "movie.mp4"


def test_pause_updatesStatusInGuiModel(spine):
    # gui 暂停 → engine 标 paused、回发 taskChanged → 该项状态更新（dataChanged）。
    spine.backend.addTask("https://example.com/movie.mp4")
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)

    spine.backend.pause(taskId)

    assert spine.taskList.data(index, TaskList.StatusRole) == "paused"


def test_remove_dropsTaskFromGuiModel(spine):
    # gui 删除 → engine 移除、回发 taskRemoved → 该项从列表消失。
    spine.backend.addTask("https://example.com/movie.mp4")
    taskId = spine.taskList.data(spine.taskList.index(0, 0), TaskList.IdRole)

    spine.backend.remove(taskId)

    assert spine.taskList.rowCount() == 0


def test_reattach_rebuildsListFromSnapshot(spine):
    # 第一个 gui 加了两个任务后“被杀”；新 gui 连上同一个 engine，attach 后靠 snapshot 看到全部。
    spine.backend.addTask("https://example.com/a.mp4")
    spine.backend.addTask("https://example.com/b.mp4")

    freshList = TaskList()
    freshBackend = Backend(spine.link, freshList)
    spine.link.connect(spine.engine.receive, freshBackend.receive)
    freshBackend.attach()

    assert freshList.rowCount() == 2


def test_detached_engineSuppressesEvents(spine):
    # gui detach 后 engine 不再发事件（省内存）；命令仍执行，重连时 snapshot 补上。
    spine.backend.detach()
    spine.backend.addTask("https://example.com/movie.mp4")
    assert spine.taskList.rowCount() == 0

    spine.backend.attach()
    assert spine.taskList.rowCount() == 1
