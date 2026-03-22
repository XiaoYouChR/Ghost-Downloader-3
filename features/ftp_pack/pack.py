from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task

from .cards import FtpResultCard, FtpTaskCard
from .task import FtpTask, parse


class FtpPack(FeaturePack):
    priority = 95
    taskType = FtpTask

    def canHandle(self, url: str) -> bool:
        return urlparse(url).scheme.lower() in {"ftp", "ftps"}

    async def parse(self, payload: dict) -> Task:
        return await parse(payload)

    def createTaskCard(self, task: Task, parent=None):
        return FtpTaskCard(task, parent)

    def createResultCard(self, task: Task, parent=None):
        return FtpResultCard(task, parent)
