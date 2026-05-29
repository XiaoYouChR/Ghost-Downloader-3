from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from .cards import FtpResultCard, FtpTaskCard
from .task import resolve as _ftpResolve


class FtpPack(FeaturePack):
    packId = "ftp"
    priority = 95

    def matches(self, url: str) -> bool:
        return urlparse(url).scheme.lower() in {"ftp", "ftps"}

    async def parse(self, payload: dict) -> Task:
        return await _ftpResolve(payload)

    def taskCard(self, task, parent=None):
        return FtpTaskCard(task, parent)

    def resultCard(self, task, parent=None):
        return FtpResultCard(task, parent)
