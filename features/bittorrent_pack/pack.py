from urllib.parse import urlparse

from loguru import logger

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.services.core_service import coreService
from .cards import BitTorrentResultCard, BTTaskCard
from .config import bittorrentConfig
from .loaders import loadLocalTorrent, resolve as _btResolve
from .web_tracker.service import webTrackerService


def _isTorrentUrl(url: str) -> bool:
    if loadLocalTorrent(url) is not None:
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
        if webTrackerService.mergedTrackers():
            return

        coreService.runCoroutine(webTrackerService.refresh(), self._onTrackersLoaded)

    def matches(self, url: str) -> bool:
        return _isTorrentUrl(url)

    async def parse(self, payload: dict) -> Task:
        return await _btResolve(payload)

    def taskCard(self, task, parent=None):
        return BTTaskCard(task, parent)

    def resultCard(self, task, parent=None):
        return BitTorrentResultCard(task, parent)

    def _onTrackersLoaded(self, result, error: str | None):
        if error:
            logger.warning("初始化 Web Tracker 失败: {}", error)
            return

        success, total = result
        logger.info(
            "已自动初始化 {} 条 Web Tracker (成功 {}/{} 个源)",
            len(webTrackerService.mergedTrackers()),
            success,
            total,
        )
