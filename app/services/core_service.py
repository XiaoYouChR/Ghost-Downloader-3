# 一个自给自足的 AsyncIO 循环, 跑在 QThread 中?
import asyncio

from PySide6.QtCore import QThread

from app.bases.models import Task
from app.services.feature_service import featuresService


class CoreService(QThread): 
    """用于接收来自前端的任务, 在 Asyncio 循环中一直等待任务"""

    def __init__(self):
        super().__init__()
        self.loop: asyncio.AbstractEventLoop = None
        self.tasks: set[Task] = set()

    async def _parseUrl(self, payload: dict):
        url = payload['url']
        function = featuresService.getParseFunction(url)
        payload = await function(payload)

    def parseUrl(self, payload: dict) -> str:
        """前端调用这玩意, 前端记录和生成了任务的 ID"""
        self.loop.create_task(self._parseUrl(payload))  # 这里不是 thread safe 的

    async def _createTask(self, payload: dict) -> Task:
        ...

    def createTask(self, payload: dict):
        """前端调用这玩意, 前端记录和生成了任务的 ID"""
        return asyncio.run_coroutine_threadsafe(self._createTask(payload), self.loop)

    def getAllTaskInfo(self) -> set:
        return self.tasks

    async def main(self):
        while True:
            await asyncio.sleep(1)

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.mainLoop = self.loop.create_task(self.main())
        self.loop.run_until_complete(self.mainLoop)

