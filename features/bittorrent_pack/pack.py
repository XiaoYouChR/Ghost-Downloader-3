from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack

from .cards import BitTorrentResultCard, BitTorrentTaskCard
from .config import bittorrentConfig
from .task import BitTorrentTask, parse


def _isTorrentUrl(url: str) -> bool:
    parsedUrl = urlparse(url)
    scheme = parsedUrl.scheme.lower()
    if scheme == "magnet":
        return "xt=urn:btih:" in url.lower()
    if scheme not in {"http", "https"}:
        return False
    return parsedUrl.path.lower().endswith(".torrent")


class BitTorrentPack(FeaturePack):
    priority = 85
    taskType = BitTorrentTask
    config = bittorrentConfig

    def canHandle(self, url: str) -> bool:
        return _isTorrentUrl(url)

    async def parse(self, payload: dict) -> BitTorrentTask:
        return await parse(payload)

    def createTaskCard(self, task: BitTorrentTask, parent=None):
        return BitTorrentTaskCard(task, parent)

    def createResultCard(self, task: BitTorrentTask, parent=None):
        return BitTorrentResultCard(task, parent)
