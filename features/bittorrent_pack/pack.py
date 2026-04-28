# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportImplicitOverride=false, reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

from loguru import logger

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput
from app.services.core_service import coreService

from .config import bittorrentConfig
from .config import getCachedWebTrackers
from .config import refreshConfiguredWebTrackers
from .task import BitTorrentTask
from .task import _buildTaskConfigFromPayload
from .task import buildBitTorrentTask
from .task import parse
from .task import resolveLocalTorrentPath


def _isTorrentUrl(source: str) -> bool:
    if resolveLocalTorrentPath(source) is not None:
        return True

    parsedUrl = urlparse(source)
    scheme = parsedUrl.scheme.lower()
    if scheme == "magnet":
        return "xt=urn:btih:" in source.lower()
    if scheme not in {"http", "https"}:
        return False
    return parsedUrl.path.lower().endswith(".torrent")


class BitTorrentPack(FeaturePack):
    priority: int = 85
    config: object = bittorrentConfig

    def accepts(self, source: str) -> bool:
        return _isTorrentUrl(source)

    async def createTask(self, data: TaskInput) -> Task | None:
        source = data.config.source.strip()
        if not self.accepts(source):
            return None
        return await buildBitTorrentTask(data)

    def owns(self, task: Task) -> bool:
        return isinstance(task, BitTorrentTask) and task.packId == self.manifest.id

    def canHandle(self, url: str) -> bool:
        return self.accepts(url)

    def canHandleTask(self, task: object) -> bool:
        return isinstance(task, BitTorrentTask) and getattr(task, "packId", "") == "bittorrent_pack"

    async def parse(self, payload: Mapping[str, object]) -> BitTorrentTask:
        return await parse(payload)

    async def createTaskFromPayload(self, payload: Mapping[str, object]) -> BitTorrentTask | None:
        config = _buildTaskConfigFromPayload(payload)
        if config is None:
            return None
        return await buildBitTorrentTask(TaskInput(config=config, hints=(dict(payload),)))

    def install(self, window: object) -> None:
        self.load(window)

    def load(self, mainWindow: object) -> None:
        _ = mainWindow
        if getCachedWebTrackers() or not coreService.isRunning():
            return

        _ = coreService.runCoroutine(
            refreshConfiguredWebTrackers(),
            self._onDefaultWebTrackersLoaded,
        )

    def createTaskCard(self, task: Task, parent: object | None = None):
        _ = task
        _ = parent
        return None

    def createResultCard(self, task: Task, parent: object | None = None):
        _ = task
        _ = parent
        return None

    def _onDefaultWebTrackersLoaded(self, result: object, error: str | None) -> None:
        if error:
            logger.warning("初始化 Web Tracker 失败: {}", error)
            return

        trackerCount = len(result) if isinstance(result, list) else 0
        logger.info("已自动初始化 {} 条 Web Tracker", trackerCount)
        webTrackerCard = getattr(bittorrentConfig, "webTrackerCard", None)
        if webTrackerCard is not None:
            webTrackerCard.refreshContent()


__all__ = ["BitTorrentPack", "parse"]
