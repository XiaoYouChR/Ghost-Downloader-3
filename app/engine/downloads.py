import asyncio
import hashlib

from app.bases.models import Task
from app.services.core_service import coreService
from app.services.feature_service import featureService


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Downloads:
    """engine 与真实下载子系统的边界：featureService 按 URL 匹配 pack 解析，coreService 跑。
    单独成模块让 engine.py 不直接拖这些；测试注入 fake 替掉整块。
    pack 的加载在 app 启动时做（featureService.load），这里只解析/调度。"""

    def parse(self, url: str):
        return featureService.parse({"url": url})

    def run(self, parsed, callback) -> None:
        coreService.runCoroutine(parsed, callback)

    def start(self, task: Task) -> None:
        coreService.createTask(task)

    def stop(self, task: Task) -> None:
        coreService.stopTask(task)

    def meta(self, task: Task) -> str:
        pack = featureService.packOf(task)
        return pack.meta(task) if pack is not None else ""

    def verify(self, task: Task, callback) -> None:
        coreService.runCoroutine(self._hash(task.outputFolder), callback)

    async def _hash(self, path: str) -> str:
        # 在线程池里算（大文件读+哈希是阻塞的），不卡 engine 的事件循环
        return await asyncio.get_event_loop().run_in_executor(None, _sha256, path)
