from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task

from .cards import FtpResultCard, FtpTaskCard
from .task import FtpTask, parse


class FtpPack(FeaturePack):
    priority = 95
    taskType = FtpTask

    def canHandle(self, url: str) -> bool:
        return urlparse(url).scheme.lower() == "ftp"

    async def parse(self, payload: dict) -> Task:
        return await parse(payload)

    def createTaskCard(self, task: Task, parent=None):
        if isinstance(task, FtpTask):
            return FtpTaskCard(task, parent)
        return None

    def createResultCard(self, task: Task, parent=None):
        if isinstance(task, FtpTask):
            return FtpResultCard(task, parent)
        return None
