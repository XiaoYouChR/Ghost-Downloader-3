from orjson import loads

from app.bases.models import Task, TaskStatus
from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event


def _httpParse(url: str):
    # 默认 parse：交给 http pack 做真实探测建 Task（async 协程，含文件名/大小）。
    from features.http_pack.pack import HttpPack

    return HttpPack().parse({"url": url})


def _coreRun(parsed, callback) -> None:
    # 默认 run：把 parse 协程丢给 coreService 的事件循环跑，完成后在 GUI 线程回调。
    from app.services.core_service import coreService

    coreService.runCoroutine(parsed, callback)


class Engine:
    """后台本体：收 command、解析建任务、回发 event。没有 gui attach 时不发事件（省内存）。
    parse / run 可注入：默认接 http pack + coreService 真跑，测试注入同步 fake 离线验证。"""

    def __init__(self, link: MemoryLink, parse=_httpParse, run=_coreRun) -> None:
        self._link = link
        self._parse = parse
        self._run = run
        self._tasks: dict[str, Task] = {}
        self._attached = False

    def receive(self, command: Command) -> None:
        if command.name == "attach":
            self._attach()
        elif command.name == "detach":
            self._attached = False
        elif command.name == "addTask":
            self._addTask(command.data["url"])
        elif command.name == "pause":
            self._setStatus(self._tasks[command.data["taskId"]], TaskStatus.PAUSED)
        elif command.name == "resume":
            self._setStatus(self._tasks[command.data["taskId"]], TaskStatus.RUNNING)
        elif command.name == "pauseAll":
            self._setAll(TaskStatus.PAUSED)
        elif command.name == "startAll":
            self._setAll(TaskStatus.RUNNING)
        elif command.name == "remove":
            self._remove(command.data["taskId"])

    def _attach(self) -> None:
        self._attached = True
        self._emit(Event("snapshot", {"tasks": [self._toWire(task) for task in self._tasks.values()]}))

    def _addTask(self, url: str) -> None:
        self._run(self._parse(url), self._onParsed)

    def _onParsed(self, task: Task | None, error: str | None) -> None:
        if error or task is None:
            return  # 解析失败先静默，后续接错误事件
        self._tasks[task.taskId] = task
        self._emit(Event("taskAdded", {"task": self._toWire(task)}))

    def _setStatus(self, task: Task, status: TaskStatus) -> None:
        task.setStatus(status)
        self._emit(Event("taskChanged", {"task": self._toWire(task)}))

    def _setAll(self, status: TaskStatus) -> None:
        for task in self._tasks.values():
            self._setStatus(task, status)

    def _remove(self, taskId: str) -> None:
        del self._tasks[taskId]
        self._emit(Event("taskRemoved", {"taskId": taskId}))

    def _toWire(self, task: Task) -> dict:
        # engine→gui 的线缆格式：序列化后的 Task 字段（跨进程时 socket 上也是这一份）
        return loads(task.serialize())

    def _emit(self, event: Event) -> None:
        # 没有 gui 在听就不发：gui 被杀后 engine 不白费力气算/发，省 CPU 与内存
        if self._attached:
            self._link.toGui(event)
