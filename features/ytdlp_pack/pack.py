from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.view.components.cards import UniversalTaskCard, UniversalResultCard

from .config import ytdlpConfig
from .task import YtDlpTask, parse


_SUPPORTED_HOSTS = {
    "youtube.com",
    "youtu.be",
    "reddit.com",
    "redd.it",
    "tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}


def _isSupportedUrl(url: str) -> bool:
    parsedUrl = urlparse(url)
    if parsedUrl.scheme.lower() not in {"http", "https"}:
        return False

    host = (parsedUrl.hostname or "").lower()
    if not host:
        return False

    return any(host == item or host.endswith(f".{item}") for item in _SUPPORTED_HOSTS)


class YtDlpPack(FeaturePack):
    priority = 60
    taskType = YtDlpTask
    config = ytdlpConfig

    def canHandle(self, url: str) -> bool:
        return _isSupportedUrl(url)

    async def parse(self, payload: dict) -> Task:
        return await parse(payload)

    def createTaskCard(self, task: Task, parent=None):
        if isinstance(task, YtDlpTask):
            return UniversalTaskCard(task, parent)
        return None

    def createResultCard(self, task: Task, parent=None):
        if isinstance(task, YtDlpTask):
            return UniversalResultCard(task, parent)
        return None
