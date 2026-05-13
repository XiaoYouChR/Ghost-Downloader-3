from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task

from .cards import FtpResultCard, FtpTaskCard
from .task import FtpTask, resolve as _ftpResolve


class FtpPack(FeaturePack):
    packId = "ftp"
    priority = 95

    def matches(self, url: str) -> bool:
        return urlparse(url).scheme.lower() in {"ftp", "ftps"}

    async def resolve(self, payload: dict) -> dict:
        return {"_task": await _ftpResolve(payload)}

    def build(self, payload: dict) -> Task:
        return payload["_task"]

    def taskCard(self, task, parent=None):
        return FtpTaskCard(task, parent)

    def resultCard(self, task, parent=None):
        return FtpResultCard(task, parent)
