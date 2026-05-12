from urllib.parse import urlparse

from loguru import logger

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.services.core_service import coreService

from .cards import BitTorrentResultCard, BTTaskCard
from .config import bittorrentConfig, getCachedWebTrackers, refreshConfiguredWebTrackers
from .task import BTTask, parse, resolveLocalTorrentPath


def _isTorrentUrl(url: str) -> bool:
    if resolveLocalTorrentPath(url) is not None:
        return True

    parsedUrl = urlparse(url)
    scheme = parsedUrl.scheme.lower()
    if scheme == "magnet":
        return "xt=urn:btih:" in url.lower()
    if scheme not in {"http", "https"}:
        return False
    return parsedUrl.path.lower().endswith(".torrent")


class BitTorrentPack(FeaturePack):
    packId = "bt"
    priority = 85
    config = bittorrentConfig

    def setup(self, mainWindow):
        if getCachedWebTrackers():
            return

        coreService.runCoroutine(
            refreshConfiguredWebTrackers(),
            self._onTrackersLoaded,
        )

    def matches(self, url: str) -> bool:
        return _isTorrentUrl(url)

    async def resolve(self, payload: dict) -> dict:
        return payload

    def build(self, payload: dict) -> Task:
        raise NotImplementedError("Use resolve() for BitTorrent tasks")

    def taskCard(self, task, parent=None):
        return BTTaskCard(task, parent)

    def resultCard(self, task, parent=None):
        return BitTorrentResultCard(task, parent)

    def _onTrackersLoaded(self, result, error: str | None):
        if error:
            logger.warning("初始化 Web Tracker 失败: {}", error)
            return

        logger.info("已自动初始化 {} 条 Web Tracker", len(result or []))
        bittorrentConfig.webTrackerCard.refreshContent()
