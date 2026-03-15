from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task

from .cards import M3U8InstallTaskCard, M3U8ResultCard, M3U8TaskCard
from .config import m3u8Config
from .task import M3U8InstallTask, M3U8Task, parse


def _isSupportedUrl(url: str) -> bool:
    parsedUrl = urlparse(url)
    if parsedUrl.scheme.lower() not in {"http", "https"}:
        return False

    loweredUrl = url.lower()
    return any(marker in loweredUrl for marker in (".m3u8", ".m3u", ".mpd"))


class M3U8Pack(FeaturePack):
    priority = 80
    taskType = (M3U8Task, M3U8InstallTask)
    config = m3u8Config

    def canHandle(self, url: str) -> bool:
        return _isSupportedUrl(url)

    async def parse(self, payload: dict) -> Task:
        return await parse(payload)

    def createTaskCard(self, task: Task, parent=None):
        if isinstance(task, M3U8InstallTask):
            return M3U8InstallTaskCard(task, parent)
        if isinstance(task, M3U8Task):
            return M3U8TaskCard(task, parent)
        return None

    def createResultCard(self, task: Task, parent=None):
        if isinstance(task, M3U8Task):
            return M3U8ResultCard(task, parent)
        return None
