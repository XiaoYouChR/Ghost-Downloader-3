from urllib.parse import urlparse

from loguru import logger

from app.bases.interfaces import FeaturePack, FileType
from app.bases.models import Task
from app.services.core_service import coreService
from app.supports import file_association
from .cards import BitTorrentResultCard, BTTaskCard
from .config import bittorrentConfig
from .loaders import loadLocalTorrent, resolve as _btResolve
from .session import btSessionService
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
        if bittorrentConfig.associateFileTypes.value:
            file_association.register(self.fileTypes())
        bittorrentConfig.associateFileTypes.valueChanged.connect(self._onAssociationToggled)

        if webTrackerService.mergedTrackers():
            return

        coreService.runCoroutine(webTrackerService.refresh(), self._onTrackersLoaded)

    def shutdown(self):
        btSessionService.shutdown()

    def _onAssociationToggled(self, enabled: bool):
        if enabled:
            file_association.register(self.fileTypes())
        else:
            file_association.unregister(self.fileTypes())

    def matches(self, url: str) -> bool:
        return _isTorrentUrl(url)

    async def parse(self, payload: dict) -> Task:
        return await _btResolve(payload)

    def taskCard(self, task, parent=None):
        return BTTaskCard(task, parent)

    def resultCard(self, task, parent=None):
        return BitTorrentResultCard(task, parent)

    def fileTypes(self):
        return [
            FileType(
                extensions=(".torrent",),
                displayName=self.tr("种子文件"),
                mimeType="application/x-bittorrent",
                icon="torrent",
            )
        ]

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
