from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task

from .cards import FtpResultCard, FtpTaskCard
from .task import FtpTask, parse


class FtpPack(FeaturePack):
    packId = "ftp"
    priority = 95

    def matches(self, url: str) -> bool:
        return urlparse(url).scheme.lower() in {"ftp", "ftps"}

    async def resolve(self, payload: dict) -> dict:
        return payload

    def build(self, payload: dict) -> Task:
        raise NotImplementedError("Use resolve() for FTP tasks")

    def taskCard(self, task, parent=None):
        return FtpTaskCard(task, parent)

    def resultCard(self, task, parent=None):
        return FtpResultCard(task, parent)
