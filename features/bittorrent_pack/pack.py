from urllib.parse import urlparse

from loguru import logger

from app.bases.interfaces import FeaturePack
from app.services.core_service import coreService

from .cards import BitTorrentResultCard, BitTorrentTaskCard
from .config import bittorrentConfig, getCachedWebTrackers, refreshConfiguredWebTrackers
from .task import BitTorrentTask, parse, resolveLocalTorrentPath


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
    priority = 85
    taskType = BitTorrentTask
    config = bittorrentConfig

    def load(self, mainWindow):
        if getCachedWebTrackers():
            return

        coreService.runCoroutine(
            refreshConfiguredWebTrackers(),
            self._onDefaultWebTrackersLoaded,
        )

    def canHandle(self, url: str) -> bool:
        return _isTorrentUrl(url)

    async def parse(self, payload: dict) -> BitTorrentTask:
        return await parse(payload)

    def createTaskCard(self, task: BitTorrentTask, parent=None):
        return BitTorrentTaskCard(task, parent)

    def createResultCard(self, task: BitTorrentTask, parent=None):
        return BitTorrentResultCard(task, parent)

    def _onDefaultWebTrackersLoaded(self, result, error: str | None):
        if error:
            logger.warning("初始化 Web Tracker 失败: {}", error)
            return

        logger.info("已自动初始化 {} 条 Web Tracker", len(result or []))
        bittorrentConfig.webTrackerCard.refreshContent()
