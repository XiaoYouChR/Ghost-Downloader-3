from pathlib import Path
from urllib.parse import urlparse

from app.bases.models import Task


class FakeDownloads:
    """测试用下载边界：不走网络、不起线程，同步建 Task 并记录 start/stop。"""

    def __init__(self, parseError: str | None = None) -> None:
        self.started: list[Task] = []
        self.stopped: list[Task] = []
        self.parsedOptions: list[dict] = []
        self.actionKind = "toggle"  # 测试可改成 finalize 验直播分派
        self._parseError = parseError

    def parse(self, url: str, options: dict | None = None) -> Task:
        if options is not None:
            self.parsedOptions.append(options)
        title = urlparse(url).path.rsplit("/", 1)[-1] or url
        path = (options or {}).get("path")  # 认引擎注入的目录，任务才不会落到真实 Downloads
        if path:
            return Task(title=title, url=url, packId="http", path=Path(path))
        return Task(title=title, url=url, packId="http")

    def run(self, parsed, callback) -> None:
        if self._parseError:
            callback(None, self._parseError)
        else:
            callback(parsed, None)

    def start(self, task: Task) -> None:
        self.started.append(task)

    def stop(self, task: Task) -> None:
        self.stopped.append(task)

    def cardChips(self, task: Task) -> list[str]:
        return []

    def cardActionKind(self, task: Task) -> str:
        return self.actionKind

    def cardSegments(self, task: Task) -> list:
        return []

    def verify(self, task: Task, callback) -> None:
        callback("test-hash", None)


class FakeStore:
    """测试用持久化边界：内存存任务，不碰文件，记录 add/remove。"""

    def __init__(self, tasks: list[Task] | None = None) -> None:
        self._tasks = list(tasks or [])
        self.added: list[Task] = []
        self.removed: list[Task] = []

    def load(self) -> list[Task]:
        return list(self._tasks)

    def add(self, task: Task) -> None:
        self.added.append(task)

    def remove(self, task: Task) -> None:
        self.removed.append(task)
