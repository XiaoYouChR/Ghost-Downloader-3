from functools import partial
from urllib.parse import urlparse

from orjson import loads
from PySide6.QtCore import QTimer

from app.bases.categories import categoryFolderById, categoryFolderFor
from app.bases.models import Task, TaskStatus
from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event
# gui 设置页读写的 config 键。引擎经注入的 Config 边界存取，不碰全局 cfg（脱 qfluentwidgets，Android-ready）
_CONFIG_KEYS = (
    "maxTaskNum", "downloadFolder", "preBlockNum", "autoSpeedUp", "SSLVerify",
    "customThemeMode", "enableClipboardListener", "checkUpdateAtStartUp", "autoRun",
    "enableSpeedLimitation", "speedLimitation", "maxReassignSize", "proxyServer", "enableCategory",
    "activeUserAgent",
)


class Engine:
    """后台本体：收 command、解析建任务、真起下载、回发 event。没有 gui attach 时不发事件（省内存）。
    downloads/store/config 都是可注入边界（默认真接，测试注入 fake/内存版离线验证）。"""

    def __init__(self, link: MemoryLink, downloads, store, config) -> None:
        self._link = link
        self._downloads = downloads
        self._store = store
        self._config = config
        self._tasks: dict[str, Task] = {}
        self._previews: dict[str, Task] = {}  # 两段式添加：解析了但未确定的任务，暂存这里
        for task in store.load():
            if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.setStatus(TaskStatus.PAUSED)  # 重启时未完成任务并未真在跑，显示为暂停
            self._tasks[task.taskId] = task
        self._attached = False
        self._snapshots: dict[str, tuple] = {}
        self._globalSpeed = -1
        self._allComplete = False  # 全部完成是边沿事件——只在「最后一个完成」那刻发一次（计划任务用）
        # 进度泵：下载在后台推进，定时轮询有变化的任务推给 gui。只在 attach 期间转（省内存）
        self._pump = QTimer()
        self._pump.setInterval(500)
        self._pump.timeout.connect(self.poll)

    def receive(self, command: Command) -> None:
        if command.name == "attach":
            self._attach()
        elif command.name == "detach":
            self._attached = False
            self._pump.stop()
        elif command.name == "addTask":
            self._addTask(command.data["url"], command.data.get("options"))
        elif command.name == "parsePreview":
            self._parsePreview(command.data["urls"], command.data.get("options"))
        elif command.name == "commit":
            self._commit(command.data.get("taskIds"))
        elif command.name == "discardPreviews":
            self._discardPreviews()
        elif command.name == "editTask":
            self._editTask(command.data["taskId"], command.data.get("options"))
        elif command.name == "editSchema":
            self._editSchema(command.data["taskId"])
        elif command.name == "redownload":
            self._redownload(command.data["taskId"])
        elif command.name == "pause":
            self._pause(self._tasks[command.data["taskId"]])
        elif command.name == "resume":
            self._resume(self._tasks[command.data["taskId"]])
        elif command.name == "toggle":
            self._toggle(self._tasks[command.data["taskId"]])
        elif command.name == "primaryAction":
            self._primaryAction(self._tasks[command.data["taskId"]])
        elif command.name == "pauseAll":
            self._pauseAll()
        elif command.name == "startAll":
            self._startAll()
        elif command.name == "remove":
            self._remove(command.data["taskId"])
        elif command.name == "clearCompleted":
            self._clearCompleted()
        elif command.name == "setSelection":
            self._setSelection(command.data["taskId"], command.data["indexes"])
        elif command.name == "setConfig":
            self._setConfig(command.data["key"], command.data["value"])
        elif command.name == "setPackSetting":
            self._downloads.applyPackSetting(command.data["packId"], command.data["key"], command.data["value"])
        elif command.name == "runPackAction":
            self._runPackAction(command.data["packId"], command.data["actionId"])
        elif command.name == "rename":
            self._rename(command.data["taskId"], command.data["title"])
        elif command.name == "setCategory":
            self._setCategory(command.data["taskId"], command.data["categoryId"])
        elif command.name == "verifyHash":
            self._downloads.verify(self._tasks[command.data["taskId"]], partial(self._onHashed, command.data["taskId"]))

    def _attach(self) -> None:
        self._attached = True
        self._emit(Event("snapshot", {"tasks": [self._toWire(task) for task in self._tasks.values()]}))
        self._emit(Event("config", {"values": {key: self._config.value(key) for key in _CONFIG_KEYS}}))
        self._emit(Event("packSettings", {"groups": self._downloads.packSettings()}))  # 各 pack 的数据驱动设置组
        self._pump.start()

    def poll(self) -> None:
        total = 0
        for task in self._tasks.values():
            _, speed, received = task.currentSnapshot()
            total += speed
            snapshot = (task.status, received, speed)
            if self._snapshots.get(task.taskId) != snapshot:
                self._snapshots[task.taskId] = snapshot
                self._changed(task)
        if total != self._globalSpeed:
            self._globalSpeed = total
            self._emit(Event("stats", {"globalSpeed": total}))

        # 全部任务完成的边沿：通知 gui（计划任务据此执行关机/重启/打开）。加新任务会重置、再完成再发。
        allComplete = bool(self._tasks) and all(
            task.status == TaskStatus.COMPLETED for task in self._tasks.values())
        if allComplete and not self._allComplete:
            self._emit(Event("allComplete", {}))
        self._allComplete = allComplete

    def _defaultOptions(self, url: str, options: dict | None = None) -> dict:
        # 注入配置里的全局下载设置——pack 从 payload 取，不再直读 cfg（脱 qfluentwidgets）。per-task 显式值优先。
        options = dict(options or {})
        if "path" not in options:  # 没显式指定才套配置目录；启用分类则按文件名归到分类子目录（引擎权威算）
            base = self._config.value("downloadFolder")
            options["path"] = (
                categoryFolderFor(urlparse(url).path.rsplit("/", 1)[-1], base, self._config.value("categoryRules"))
                if self._config.value("enableCategory") else base
            )
        options.setdefault("preBlockNum", self._config.value("preBlockNum"))
        return options

    def _addTask(self, url: str, options: dict | None = None) -> None:
        # 内联快速添加：解析即开始（不走两段式预览）
        self._downloads.run(self._downloads.parse(url, self._defaultOptions(url, options)), self._onParsed)

    def _parsePreview(self, urls: list[str], options: dict | None = None) -> None:
        # 两段式添加第一步：逐条解析、暂存进 _previews，不落任务/不开始；回发预览给 gui，确定后才 commit。
        # options（目录/线程等）在解析时注入——pack 据此建 stage，不必事后改 path（避开时序坑）。
        for url in urls:
            self._downloads.run(self._downloads.parse(url, self._defaultOptions(url, options)), partial(self._onPreviewParsed, url))

    def _onPreviewParsed(self, url: str, task: Task | None, error: str | None) -> None:
        if error or task is None:
            self._emit(Event("previewError", {"url": url, "reason": error or "无法解析该链接"}))
            return
        self._previews[task.taskId] = task
        self._emit(Event("previewParsed", {"task": self._toWire(task)}))

    def _commit(self, taskIds: list[str] | None = None) -> None:
        # 确定：把预览转成真任务、落盘+开始。taskIds=None 提交全部预览。
        for taskId in (taskIds if taskIds is not None else list(self._previews)):
            task = self._previews.pop(taskId, None)
            if task is not None:
                self._onParsed(task, None)

    def _discardPreviews(self) -> None:
        for task in self._previews.values():
            task.cleanup()
        self._previews.clear()

    def _onParsed(self, task: Task | None, error: str | None) -> None:
        if error or task is None:
            self._emit(Event("addError", {"reason": error or "无法解析该链接"}))
            return
        self._tasks[task.taskId] = task
        self._store.add(task)
        self._downloads.start(task)
        self._emit(Event("taskAdded", {"task": self._toWire(task)}))

    def _editSchema(self, taskId: str) -> None:
        # gui 要编辑某任务/预览：把该任务的编辑卡 schema 回发，gui 据此渲染编辑框
        task = self._tasks.get(taskId) or self._previews.get(taskId)
        if task is not None:
            self._emit(Event("editSchema", {"taskId": taskId, "schema": task.editorSchema()}))

    def _editTask(self, taskId: str, options: dict | None = None) -> None:
        # 编辑任务：链接变了才按新 url 重解析换 stage（新资源，大小/分段全变）；
        # 只改设置（标头/代理/轨道/密钥/目录）则就地 applySettings——免重解析、不丢进度（M3U8 尤其要躲开重新枚举流）。
        isPreview = taskId in self._previews
        old = self._tasks.get(taskId) or self._previews.get(taskId)
        if old is None:
            return
        options = dict(options or {})
        url = options.pop("url", old.url)
        if url != old.url:
            if not isPreview:
                self._downloads.stop(old)
            options.setdefault("path", str(old.path))  # 重解析沿用现有目录（replaceWith 保留 path）
            options.setdefault("preBlockNum", self._config.value("preBlockNum"))
            self._downloads.run(self._downloads.parse(url, options), partial(self._onReparsed, old, isPreview))
            return

        # 选了分类只传 categoryId，引擎按配置目录权威算出分类子目录（gui 不碰目录拼接）。
        if "category" in options:
            folder = categoryFolderById(
                options["category"], self._config.value("downloadFolder"), self._config.value("categoryRules"))
            if folder:
                options = {**options, "path": folder}

        # 链接没变——就地应用设置。跑着的先停、应用后再起，让新设置（如换代理）即时生效且不丢已下字节。
        wasRunning = not isPreview and old.status == TaskStatus.RUNNING
        if wasRunning:
            self._downloads.stop(old)
        old.applySettings(options)
        if isPreview:
            self._emit(Event("previewChanged", {"task": self._toWire(old)}))
        else:
            self._store.add(old)
            if wasRunning:
                self._downloads.start(old)
            self._changed(old)

    def _redownload(self, taskId: str) -> None:
        # 重新下载（复刻原版）：停旧下载 → 按原 url 重解析 → 换进旧任务（cleanup 删旧分片、进度归零）→ 重新开始。
        old = self._tasks.get(taskId)
        if old is None:
            return
        self._downloads.stop(old)
        options = self._defaultOptions(old.url, {"path": str(old.path)})
        self._downloads.run(self._downloads.parse(old.url, options), partial(self._onRedownloaded, old))

    def _onRedownloaded(self, old: Task, task: Task | None, error: str | None) -> None:
        if error or task is None:
            self._emit(Event("addError", {"reason": error or "无法解析该链接"}))
            return
        old.replaceWith(task)  # 删旧分片、换上全新 stage（进度归零）
        old.setStatus(TaskStatus.RUNNING)
        self._store.add(old)
        self._downloads.start(old)
        self._changed(old)

    def _onReparsed(self, old: Task, isPreview: bool, task: Task | None, error: str | None) -> None:
        if error or task is None:
            self._emit(Event("addError", {"reason": error or "无法解析该链接"}))
            return
        if not old.tryKeepProgress(task):  # 结构相符（如刷新过期 CDN url）能保住进度，否则整换
            old.replaceWith(task)
        if isPreview:  # 预览编辑：只更新预览展示，不落盘/不开始（确定时才 commit）
            self._emit(Event("previewChanged", {"task": self._toWire(old)}))
        else:
            self._store.add(old)  # 换了 url/stages，重新落盘
            self._changed(old)

    def _pause(self, task: Task) -> None:
        task.setStatus(TaskStatus.PAUSED)
        self._downloads.stop(task)
        self._changed(task)

    def _resume(self, task: Task) -> None:
        task.setStatus(TaskStatus.RUNNING)
        self._downloads.start(task)
        self._changed(task)

    def _toggle(self, task: Task) -> None:
        # 卡片的单个开关：在跑就暂停，否则继续。判断留在引擎（它持状态机），view 只发意图
        (self._pause if task.status == TaskStatus.RUNNING else self._resume)(task)

    def _primaryAction(self, task: Task) -> None:
        # 主按钮的统一意图：pack 声明 finalize（如直播）就停止收尾，否则普通暂停/继续。判断在引擎
        if self._downloads.cardActionKind(task) == "finalize":
            self._finalize(task)
        else:
            self._toggle(task)

    def _finalize(self, task: Task) -> None:
        # 直播无暂停语义：停止即让 worker 收尾标 COMPLETED，不置 PAUSED（避免闪烁）；状态由进度泵带回
        self._downloads.stop(task)

    def _pauseAll(self) -> None:
        for task in self._tasks.values():
            self._pause(task)

    def _startAll(self) -> None:
        for task in self._tasks.values():
            self._resume(task)

    def _remove(self, taskId: str) -> None:
        self._store.remove(self._tasks[taskId])
        del self._tasks[taskId]
        self._snapshots.pop(taskId, None)
        self._emit(Event("taskRemoved", {"taskId": taskId}))

    def _clearCompleted(self) -> None:
        completed = [taskId for taskId, task in self._tasks.items() if task.status == TaskStatus.COMPLETED]
        for taskId in completed:
            self._remove(taskId)

    def _setSelection(self, taskId: str, indexes: list) -> None:
        # 选下载哪些文件（BT 种子/FTP 目录多文件）。预览还没提交——只更新预览展示、不落库。
        task = self._tasks.get(taskId) or self._previews.get(taskId)
        if task is None:
            return
        task.setSelection(list(indexes))
        if taskId in self._previews:
            self._emit(Event("previewChanged", {"task": self._toWire(task)}))
        else:
            self._changed(task)

    def _setConfig(self, key: str, value) -> None:
        self._config.set(key, value)
        self._emit(Event("config", {"values": {key: self._config.value(key)}}))

    def _rename(self, taskId: str, title: str) -> None:
        # 改文件名（复刻原版结果卡/任务卡内联改名）。预览还没落盘——只更新展示、不落库。
        task = self._tasks.get(taskId) or self._previews.get(taskId)
        if task is None:
            return
        task.setTitle(title)
        if taskId in self._previews:
            self._emit(Event("previewChanged", {"task": self._toWire(task)}))
        else:
            self._store.add(task)  # 改名要落盘
            self._changed(task)

    def _runPackAction(self, packId: str, actionId: str) -> None:
        # pack 设置区的动作按钮。目前只有「一键安装」：跑 pack 的安装协程，结果当普通任务加进列表+开始。
        if actionId == "install":
            coroutine = self._downloads.installTask(packId)
            if coroutine is not None:
                self._downloads.run(coroutine, self._onParsed)

    def _setCategory(self, taskId: str, categoryId: str) -> None:
        # 「移动到分类」：只重新打分类标签，不动已下文件/目录（复刻原版——文件已落盘，仅改归类）。
        task = self._tasks.get(taskId)
        if task is None:
            return
        task.category = categoryId
        self._store.add(task)  # 标签变了要落盘
        self._changed(task)

    def _onHashed(self, taskId: str, digest: str | None, error: str | None) -> None:
        if error or not digest:
            return
        self._emit(Event("hashResult", {"taskId": taskId, "hash": digest}))

    def _changed(self, task: Task) -> None:
        self._emit(Event("taskChanged", {"task": self._toWire(task)}))

    def _toWire(self, task: Task) -> dict:
        # engine→gui 的线缆格式：序列化字段 + 当前进度/速度（跨进程时 socket 上也是这一份）
        data = loads(task.serialize())
        progress, speed, received = task.currentSnapshot()
        if task.status == TaskStatus.COMPLETED:
            progress = 100.0
            received = task.fileSize
        elif task.fileSize > 0:
            progress = min(100.0, received / task.fileSize * 100)
        data["progress"] = progress
        data["speed"] = speed
        data["received"] = received
        data["error"] = task.lastError
        data["chips"] = self._downloads.cardChips(task)  # pack 专属展示串列表（BT 的 Peers/Seeds 等）
        data["actionKind"] = self._downloads.cardActionKind(task)  # 主按钮语义：toggle / finalize(直播)
        data["segments"] = self._downloads.cardSegments(task)  # HTTP 多线程分段进度（百分比区间）
        return data

    def _emit(self, event: Event) -> None:
        # 没有 gui 在听就不发：gui 被杀后 engine 不白费力气算/发，省 CPU 与内存
        if self._attached:
            self._link.toGui(event)
