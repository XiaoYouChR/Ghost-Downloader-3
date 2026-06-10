from functools import partial

from orjson import loads
from PySide6.QtCore import QTimer

from app.bases.models import Task, TaskStatus
from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event
from app.supports.config import cfg

# 设置页目前直接读写真 cfg（同进程缝先行）；Config 存储是日后拆进程/headless 的目标
_CONFIG_KEYS = (
    "maxTaskNum", "downloadFolder", "preBlockNum", "autoSpeedUp", "SSLVerify",
    "customThemeMode", "enableClipboardListener", "checkUpdateAtStartUp", "autoRun",
    "enableSpeedLimitation", "maxReassignSize", "proxyServer",
)


class Engine:
    """后台本体：收 command、解析建任务、真起下载、回发 event。没有 gui attach 时不发事件（省内存）。
    downloads 是与下载子系统的边界（默认真接 coreService+http pack，测试注入 fake 离线验证）。"""

    def __init__(self, link: MemoryLink, downloads, store) -> None:
        self._link = link
        self._downloads = downloads
        self._store = store
        self._tasks: dict[str, Task] = {}
        for task in store.load():
            if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.setStatus(TaskStatus.PAUSED)  # 重启时未完成任务并未真在跑，显示为暂停
            self._tasks[task.taskId] = task
        self._attached = False
        self._snapshots: dict[str, tuple] = {}
        self._globalSpeed = -1
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
            self._addTask(command.data["url"])
        elif command.name == "pause":
            self._pause(self._tasks[command.data["taskId"]])
        elif command.name == "resume":
            self._resume(self._tasks[command.data["taskId"]])
        elif command.name == "toggle":
            self._toggle(self._tasks[command.data["taskId"]])
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
        elif command.name == "rename":
            self._rename(command.data["taskId"], command.data["title"])
        elif command.name == "verifyHash":
            self._downloads.verify(self._tasks[command.data["taskId"]], partial(self._onHashed, command.data["taskId"]))

    def _attach(self) -> None:
        self._attached = True
        self._emit(Event("snapshot", {"tasks": [self._toWire(task) for task in self._tasks.values()]}))
        self._emit(Event("config", {"values": {key: getattr(cfg, key).value for key in _CONFIG_KEYS}}))
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

    def _addTask(self, url: str) -> None:
        self._downloads.run(self._downloads.parse(url), self._onParsed)

    def _onParsed(self, task: Task | None, error: str | None) -> None:
        if error or task is None:
            self._emit(Event("addError", {"reason": error or "无法解析该链接"}))
            return
        self._tasks[task.taskId] = task
        self._store.add(task)
        self._downloads.start(task)
        self._emit(Event("taskAdded", {"task": self._toWire(task)}))

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
        task = self._tasks[taskId]
        task.setSelection(list(indexes))
        self._changed(task)

    def _setConfig(self, key: str, value) -> None:
        getattr(cfg, key).value = value
        self._emit(Event("config", {"values": {key: getattr(cfg, key).value}}))

    def _rename(self, taskId: str, title: str) -> None:
        task = self._tasks[taskId]
        task.setTitle(title)
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
        return data

    def _emit(self, event: Event) -> None:
        # 没有 gui 在听就不发：gui 被杀后 engine 不白费力气算/发，省 CPU 与内存
        if self._attached:
            self._link.toGui(event)
