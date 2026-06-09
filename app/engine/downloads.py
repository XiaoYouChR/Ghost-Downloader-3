from app.bases.models import Task
from app.services.core_service import coreService
from features.http_pack.pack import HttpPack


class Downloads:
    """engine 与真实下载子系统（coreService + http pack）的边界。
    单独成模块，让 engine.py 不直接拖 coreService/网络依赖；测试注入 fake 替掉整块。"""

    def parse(self, url: str):
        return HttpPack().parse({"url": url})

    def run(self, parsed, callback) -> None:
        coreService.runCoroutine(parsed, callback)

    def start(self, task: Task) -> None:
        coreService.createTask(task)

    def stop(self, task: Task) -> None:
        coreService.stopTask(task)
