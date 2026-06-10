from PySide6.QtTest import QSignalSpy

from app.bases.models import TaskStatus
from app.engine.config import Config
from app.engine.engine import Engine
from app.engine.settings import GLOBAL_SETTINGS
from app.gui.backend import Backend
from app.gui.task_list import TaskList
from app.protocol.link import MemoryLink
from app.protocol.message import Event
from fakes import FakeDownloads, FakeStore


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

    assert spine.taskList.data(index, TaskList.StatusRole) == "PAUSED"


def test_config_event_updatesBackendProperties(spine):
    # engine 下发 config → 落进 backend.config 这个 PropertyMap → QML 反射式绑定显示。
    spine.backend.receive(Event("config", {"values": {
        "maxTaskNum": 8, "downloadFolder": "/dl", "preBlockNum": 16,
        "autoSpeedUp": False, "SSLVerify": False,
    }}))

    config = spine.backend.config
    assert config.value("maxTaskNum") == 8
    assert config.value("downloadFolder") == "/dl"
    assert config.value("preBlockNum") == 16
    assert config.value("autoSpeedUp") is False
    assert config.value("SSLVerify") is False


def test_setConfig_writesToInjectedConfig(spine):
    # 引擎经注入的 Config 边界存配置（不碰全局 cfg）；改动回流到 backend.config 给设置页。
    spine.backend.setConfig("preBlockNum", 32)

    assert spine.config.value("preBlockNum") == 32
    assert spine.backend.config.value("preBlockNum") == 32


def test_stats_updatesGlobalSpeedText(spine):
    # 进度泵汇总全局速度 → stats 事件 → backend 暴露给工具栏徽章。
    spine.backend.receive(Event("stats", {"globalSpeed": 2048}))

    assert spine.backend.globalSpeedText == "2.00 KB/s"


def test_poll_pushesStatusChangeToGui(spine):
    # 下载在后台推进时 worker 改 task 状态；poll 检测到变化就发 taskChanged，gui 实时反映。
    spine.backend.addTask("https://example.com/movie.mp4")
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)
    spine.engine.poll()

    spine.engine._tasks[taskId].setStatus(TaskStatus.COMPLETED)
    spine.engine.poll()

    assert spine.taskList.data(index, TaskList.StatusRole) == "COMPLETED"


def test_poll_silentWhenUnchanged(spine):
    # 进度泵去重：快照没变就不发 taskChanged（省 CPU，不刷 gui）。
    spine.backend.addTask("https://example.com/movie.mp4")
    spine.engine.poll()  # 首轮记下快照

    spy = QSignalSpy(spine.taskList.dataChanged)
    spine.engine.poll()  # 快照未变

    assert spy.count() == 0


def test_completedTask_showsFullProgress(spine):
    # 完成态进度归 100（即便末段字节计数有差）。
    spine.backend.addTask("https://example.com/movie.mp4")
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)

    spine.engine._tasks[taskId].setStatus(TaskStatus.COMPLETED)
    spine.engine.poll()

    assert spine.taskList.data(index, TaskList.ProgressRole) == 100.0


def test_addTask_startsDownload(spine):
    # 加任务即交给下载边界真起（默认 coreService.createTask）。
    spine.backend.addTask("https://example.com/movie.mp4")

    assert len(spine.downloads.started) == 1


def test_pause_stopsDownload(spine):
    # 暂停即让下载边界真停（默认 coreService.stopTask）。
    spine.backend.addTask("https://example.com/movie.mp4")
    taskId = spine.taskList.data(spine.taskList.index(0, 0), TaskList.IdRole)

    spine.backend.pause(taskId)

    assert len(spine.downloads.stopped) == 1


def test_resume_setsTaskRunning(spine):
    # 暂停后再继续 → 状态回到 RUNNING（pause 的对偶，卡片按钮据此切换）。
    spine.backend.addTask("https://example.com/movie.mp4")
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)
    spine.backend.pause(taskId)

    spine.backend.resume(taskId)

    assert spine.taskList.data(index, TaskList.StatusRole) == "RUNNING"


def test_runningRole_reflectsStatus(spine):
    # 卡片靠 running 这个布尔决定显示「暂停」还是「继续」（判断在 Python，QML 只绑定）。
    spine.backend.addTask("https://example.com/movie.mp4")
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)
    assert spine.taskList.data(index, TaskList.RunningRole) is False

    spine.backend.resume(taskId)

    assert spine.taskList.data(index, TaskList.RunningRole) is True


def test_pauseAll_pausesEveryTask(spine):
    spine.backend.addTask("https://example.com/a.mp4")
    spine.backend.addTask("https://example.com/b.mp4")

    spine.backend.pauseAll()

    for row in range(spine.taskList.rowCount()):
        assert spine.taskList.data(spine.taskList.index(row, 0), TaskList.StatusRole) == "PAUSED"


def test_startAll_runsEveryTask(spine):
    spine.backend.addTask("https://example.com/a.mp4")
    spine.backend.addTask("https://example.com/b.mp4")
    spine.backend.pauseAll()

    spine.backend.startAll()

    for row in range(spine.taskList.rowCount()):
        assert spine.taskList.data(spine.taskList.index(row, 0), TaskList.StatusRole) == "RUNNING"


def test_verifyHash_returnsHashToGui(spine):
    # 校验命令 → 引擎算文件哈希 → hashResult 事件 → backend.hashText 给对话框显示。
    spine.backend.addTask("https://example.com/a.mp4")
    taskId = spine.taskList.data(spine.taskList.index(0, 0), TaskList.IdRole)

    spine.backend.verifyHash(taskId)

    assert spine.backend.hashText == "test-hash"


def test_rename_changesTitle(spine):
    # 重命名任务 → 标题更新（经 setTitle，会过 toSafeFilename）。
    spine.backend.addTask("https://example.com/movie.mp4")
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)

    spine.backend.rename(taskId, "renamed.mp4")

    assert spine.taskList.data(index, TaskList.TitleRole) == "renamed.mp4"


def test_clearCompleted_removesOnlyCompleted(spine):
    # 清空已完成只删 COMPLETED，其余留下。
    spine.backend.addTask("https://example.com/a.mp4")
    spine.backend.addTask("https://example.com/b.mp4")
    ids = [spine.taskList.data(spine.taskList.index(i, 0), TaskList.IdRole) for i in range(2)]
    spine.engine._tasks[ids[0]].setStatus(TaskStatus.COMPLETED)

    spine.backend.clearCompleted()

    assert spine.taskList.rowCount() == 1


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


def test_addTaskWithOptions_passesOptionsToParse(spine):
    # 「新建任务」对话框带选项（下载目录等）→ 经缝传到引擎 → 并进 parse payload。
    spine.backend.addTaskWithOptions("https://example.com/movie.mp4", {"path": "/custom"})

    assert spine.downloads.parsedOptions == [{"path": "/custom"}]
    assert spine.taskList.rowCount() == 1


def test_toggle_pausesRunningResumesPaused(spine):
    # 卡片只发“切换”意图，由引擎据状态机决定暂停还是继续（view 不做判断）。
    spine.backend.addTask("https://example.com/movie.mp4")
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)
    spine.backend.resume(taskId)

    spine.backend.toggle(taskId)
    assert spine.taskList.data(index, TaskList.StatusRole) == "PAUSED"

    spine.backend.toggle(taskId)
    assert spine.taskList.data(index, TaskList.StatusRole) == "RUNNING"


def test_addTask_parseFailure_notifiesGui(qapp):
    # 链接解析失败 → engine 发 addError → backend.taskAddFailed 触发（gui 弹浮层提示），不留半个任务。
    link = MemoryLink()
    taskList = TaskList()
    backend = Backend(link, taskList)
    engine = Engine(link, FakeDownloads(parseError="无法解析该链接"), FakeStore(), Config(GLOBAL_SETTINGS))
    link.connect(engine.receive, backend.receive)
    backend.attach()

    spy = QSignalSpy(backend.taskAddFailed)
    backend.addTask("not-a-valid-url")

    assert taskList.rowCount() == 0
    assert spy.count() == 1
