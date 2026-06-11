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

    assert spine.downloads.parsedOptions[0]["path"] == "/custom"  # per-task 值优先
    assert spine.taskList.rowCount() == 1


def test_addTask_injectsConfigGlobals(spine):
    # 不带选项的添加：引擎把配置里的全局设置（目录/分块数）注入 parse payload，pack 不再直读 cfg（脱 cfg）。
    spine.config.set("downloadFolder", "/cfg-default")
    spine.config.set("preBlockNum", 16)
    spine.backend.addTask("https://example.com/movie.mp4")

    assert spine.downloads.parsedOptions == [{"path": "/cfg-default", "preBlockNum": 16}]


def test_editTask_reparsesAndReplacesTask(spine, tmp_path):
    # 编辑任务改链接 → 引擎重解析 → replaceWith 换 url/title/stages，保留同一 taskId。
    # 落临时目录：replaceWith 的 cleanup（清旧分片）不碰真实 Downloads。
    spine.config.set("downloadFolder", str(tmp_path))
    spine.backend.addTask("https://example.com/old.zip")
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)

    spine.backend.editTask(taskId, {"url": "https://example.com/new.mkv"})

    assert spine.taskList.data(index, TaskList.TitleRole) == "new.mkv"
    assert spine.taskList.data(index, TaskList.IdRole) == taskId


def test_editTask_appliesSettingsInPlaceWithoutReparsing(spine, tmp_path):
    # 链接没变、只改设置（如目录）→ 就地 applySettings，不触发重解析（免重新枚举流/不丢进度）。
    spine.config.set("downloadFolder", str(tmp_path))
    spine.backend.addTask("https://example.com/a.zip")
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)
    parsesBefore = len(spine.downloads.parsedOptions)

    spine.backend.editTask(taskId, {"path": str(tmp_path / "sub")})

    assert len(spine.downloads.parsedOptions) == parsesBefore  # 没再 parse
    assert spine.taskList.data(index, TaskList.IdRole) == taskId


def test_moveSelectedToCategory_retagsLabelWithoutMovingFiles(spine, tmp_path):
    # 批量「移动到分类」：只改 task.category 标签，不动已下文件的目录（文件已落盘，仅重新归类）。
    spine.config.set("downloadFolder", str(tmp_path))
    spine.backend.addTask("https://example.com/movie.mp4")  # 默认归类 cat_video
    index = spine.taskList.index(0, 0)
    taskId = spine.taskList.data(index, TaskList.IdRole)
    pathBefore = spine.engine._tasks[taskId].path
    spine.taskList.toggleSelect(taskId)

    spine.backend.moveSelectedToCategory("cat_other")

    assert spine.taskList.data(index, TaskList.CategoryRole) == "cat_other"
    assert spine.engine._tasks[taskId].path == pathBefore  # 目录没动


def test_redownloadSelected_restartsEachSelected(spine, tmp_path):
    # 批量「重新下载」：每个选中的任务都重解析重开（仍是原任务）。
    spine.config.set("downloadFolder", str(tmp_path))
    spine.backend.addTask("https://example.com/a.zip")
    spine.backend.addTask("https://example.com/b.zip")
    spine.taskList.selectAll()
    startedBefore = len(spine.downloads.started)

    spine.backend.redownloadSelected()

    assert len(spine.downloads.started) == startedBefore + 2  # 两个都重下


def test_addTask_appliesCategoryFolderWhenEnabled(spine):
    # 启用分类：按文件名扩展把下载目录归到分类子目录（引擎权威算，pack 收到的就是归好类的 path）。
    spine.config.set("downloadFolder", "/dl")
    spine.config.set("enableCategory", True)
    spine.backend.addTask("https://example.com/movie.mp4")

    assert spine.downloads.parsedOptions[0]["path"] == "/dl/Video"


def test_addTask_noCategoryFolderWhenDisabled(spine):
    spine.config.set("downloadFolder", "/dl")
    spine.config.set("enableCategory", False)
    spine.backend.addTask("https://example.com/movie.mp4")

    assert spine.downloads.parsedOptions[0]["path"] == "/dl"


def test_addTask_explicitPathBeatsCategory(spine):
    # 用户显式指定目录时不套分类（per-task 值优先）。
    spine.config.set("enableCategory", True)
    spine.backend.addTaskWithOptions("https://example.com/movie.mp4", {"path": "/custom"})

    assert spine.downloads.parsedOptions[0]["path"] == "/custom"


def test_editSchema_emitsTaskEditorSchema(spine):
    # gui 请求编辑某任务 → 引擎回发该任务的编辑卡 schema（基类 Task 无编辑卡→空，pack 子类才有内容）。
    spine.backend.addTask("https://example.com/a.mp4")
    taskId = spine.taskList.data(spine.taskList.index(0, 0), TaskList.IdRole)
    captured = []
    spine.backend.editSchemaReady.connect(lambda tid, schema: captured.append((tid, schema)))

    spine.backend.requestEditSchema(taskId)

    assert captured[-1][0] == taskId
    assert isinstance(captured[-1][1], list)


def test_parsePreview_holdsWithoutCommitting(spine):
    # 两段式添加第一步：解析多条链接进预览，但不落任务列表、不开始下载。
    spine.backend.parsePreview(["https://example.com/a.mp4", "https://example.com/b.mkv"])

    assert spine.backend.previewList.rowCount() == 2
    assert spine.taskList.rowCount() == 0  # 未提交
    assert len(spine.downloads.started) == 0  # 未开始


def test_redownload_reparsesAndRestarts(spine, tmp_path):
    # 右键「重新下载」：停旧 → 重解析 → 清旧分片换新 stage → 重新开始（仍是同一任务）。
    spine.config.set("downloadFolder", str(tmp_path))
    spine.backend.addTask("https://example.com/a.zip")
    taskId = spine.taskList.data(spine.taskList.index(0, 0), TaskList.IdRole)
    startedBefore = len(spine.downloads.started)

    spine.backend.redownload(taskId)

    assert len(spine.downloads.started) == startedBefore + 1  # 重新开始
    assert spine.taskList.rowCount() == 1  # 还是这一个任务
    assert spine.taskList.data(spine.taskList.index(0, 0), TaskList.StatusRole) == "RUNNING"


def test_editPreview_updatesPreviewWithoutCommitting(spine, tmp_path):
    # per-URL 编辑：解析后、提交前改某条预览的链接 → 预览原地更新，不落任务/不开始。
    spine.config.set("downloadFolder", str(tmp_path))  # replaceWith 的 cleanup 落临时目录
    spine.backend.parsePreview(["https://example.com/old.zip"])
    pv = spine.backend.previewList
    previewId = pv.data(pv.index(0, 0), TaskList.IdRole)

    spine.backend.editTask(previewId, {"url": "https://example.com/new.mkv"})

    assert spine.taskList.rowCount() == 0  # 未提交
    assert pv.rowCount() == 1  # 仍是预览
    assert pv.data(pv.index(0, 0), TaskList.TitleRole) == "new.mkv"


def test_previewCategoryOverride_routesPathThroughCommit(spine, tmp_path):
    # per-URL 分类钮：gui 只回传 categoryId，引擎按配置目录权威算出分类子目录 → 提交后落在那。
    spine.config.set("downloadFolder", str(tmp_path))
    spine.backend.parsePreview(["https://example.com/a.zip"])
    pv = spine.backend.previewList
    previewId = pv.data(pv.index(0, 0), TaskList.IdRole)

    spine.backend.editTask(previewId, {"category": "cat_video"})
    spine.backend.commit()

    assert spine.store.added[-1].path == tmp_path / "Video"


def test_selectFilesOnPreview_keepsItUncommitted(spine):
    # 多文件预览（BT/FTP）选文件：走选文件框确认 → setSelection 落在预览上，不提交、不开始。
    # 旧实现 _setSelection 直接 self._tasks[id] 会 KeyError；这条守 setSelection 认预览。
    spine.backend.parsePreview(["magnet:?xt=urn:btih:abc"])
    pv = spine.backend.previewList
    previewId = pv.data(pv.index(0, 0), TaskList.IdRole)

    spine.backend.editFiles(previewId)  # 选文件框数据源能在预览列表里找到这条
    spine.backend.confirmFiles()  # 确认 → setSelection 命令

    assert spine.taskList.rowCount() == 0  # 未提交
    assert pv.rowCount() == 1  # 仍是预览


def test_renamePreview_updatesTitleWithoutCommitting(spine):
    # 解析后、提交前内联改名 → 预览原地改文件名，不落任务列表/不开始下载。
    spine.backend.parsePreview(["https://example.com/old.zip"])
    pv = spine.backend.previewList
    previewId = pv.data(pv.index(0, 0), TaskList.IdRole)

    spine.backend.rename(previewId, "renamed.zip")

    assert spine.taskList.rowCount() == 0  # 未提交
    assert pv.data(pv.index(0, 0), TaskList.TitleRole) == "renamed.zip"


def test_commit_movesPreviewsToTasksAndStarts(spine):
    # 第二步：确定 → 预览转成真任务、落盘+开始，预览清空。
    spine.backend.parsePreview(["https://example.com/a.mp4"])
    spine.backend.commit()

    assert spine.taskList.rowCount() == 1
    assert len(spine.downloads.started) == 1
    assert spine.backend.previewList.rowCount() == 0


def test_discardPreviews_clearsWithoutCommitting(spine):
    # 取消 → 丢弃预览，不留痕。
    spine.backend.parsePreview(["https://example.com/a.mp4"])
    spine.backend.discardPreviews()

    assert spine.backend.previewList.rowCount() == 0
    assert spine.taskList.rowCount() == 0
    assert len(spine.downloads.started) == 0


def test_addTask_usesInjectedCustomCategoryRules(spine):
    # 引擎按注入的自定义分类规则归类（从 cfg 播种来；共存期用户在旧 app 设的规则也认）。
    spine.config.set("downloadFolder", "/dl")
    spine.config.set("enableCategory", True)
    spine.config.set("categoryRules", [{"extensions": ["iso"], "folder": "{default}/Disks"}])
    spine.backend.addTask("https://example.com/ubuntu.iso")

    assert spine.downloads.parsedOptions[0]["path"] == "/dl/Disks"


def test_addTaskWithOptions_emptyOptionsStillAppliesCategory(spine):
    # 新建对话框留空目录时传空 options → 引擎照样按类型归类（对话框必须省略空 path，别传 {path:""}）。
    spine.config.set("downloadFolder", "/dl")
    spine.config.set("enableCategory", True)
    spine.backend.addTaskWithOptions("https://example.com/song.mp3", {})

    assert spine.downloads.parsedOptions[0]["path"] == "/dl/Audio"


def test_primaryAction_togglesByDefault(spine):
    # 普通任务 actionKind=toggle：卡片主按钮 → primaryAction → 暂停/继续。
    spine.backend.addTask("https://example.com/movie.mp4")
    taskId = spine.taskList.data(spine.taskList.index(0, 0), TaskList.IdRole)
    spine.backend.resume(taskId)

    spine.backend.primaryAction(taskId)

    assert spine.taskList.data(spine.taskList.index(0, 0), TaskList.StatusRole) == "PAUSED"


def test_primaryAction_finalizesWhenPackDeclaresIt(spine):
    # pack 声明 actionKind=finalize（如直播）：primaryAction 走停止收尾，不置 PAUSED（worker 收尾标完成）。
    spine.downloads.actionKind = "finalize"
    spine.backend.addTask("https://example.com/live.m3u8")
    taskId = spine.taskList.data(spine.taskList.index(0, 0), TaskList.IdRole)
    spine.backend.resume(taskId)

    spine.backend.primaryAction(taskId)

    assert len(spine.downloads.stopped) == 1
    assert spine.taskList.data(spine.taskList.index(0, 0), TaskList.StatusRole) != "PAUSED"


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
