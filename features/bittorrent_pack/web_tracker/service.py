import asyncio

from PySide6.QtCore import QObject, Signal

from app.supports.config import cfg
from ..config import bittorrentConfig
from ..trackers import (
    fetchWebTrackers,
    mergeTrackers,
    parseTrackerText,
)


class WebTrackerService(QObject):
    trackersChanged = Signal()

    def sourceUrls(self) -> list[str]:
        return list(bittorrentConfig.webTrackerSources.value)

    def customTrackers(self) -> list[str]:
        return parseTrackerText(bittorrentConfig.webTrackerCustomList.value)

    def cachedCount(self, url: str) -> int | None:
        cache = self._sourceCache()
        if url not in cache:
            return None
        return len(cache[url])

    def mergedTrackers(self) -> list[str]:
        cache = self._sourceCache()
        return mergeTrackers(*cache.values(), self.customTrackers())

    def setSourceUrls(self, urls: list[str]) -> None:
        cfg.set(bittorrentConfig.webTrackerSources, urls)
        cache = self._sourceCache()
        prunedCache = {url: trackers for url, trackers in cache.items() if url in urls}
        if prunedCache != cache:
            cfg.set(bittorrentConfig.webTrackerSourceCache, prunedCache)
        self.trackersChanged.emit()

    def setCustomTrackers(self, trackers: list[str]) -> None:
        cfg.set(bittorrentConfig.webTrackerCustomList, "\n".join(trackers))
        self.trackersChanged.emit()

    async def refresh(self) -> tuple[int, int]:
        urls = self.sourceUrls()
        if not urls:
            self.trackersChanged.emit()
            return 0, 0

        results = await asyncio.gather(
            *(fetchWebTrackers(url) for url in urls),
            return_exceptions=True,
        )

        oldCache = self._sourceCache()
        newCache: dict[str, list[str]] = {}
        successCount = 0
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                if url in oldCache:
                    newCache[url] = oldCache[url]
            else:
                newCache[url] = result
                successCount += 1

        cfg.set(bittorrentConfig.webTrackerSourceCache, newCache)
        self.trackersChanged.emit()
        return successCount, len(urls)

    def _sourceCache(self) -> dict[str, list[str]]:
        return dict(bittorrentConfig.webTrackerSourceCache.value)


webTrackerService = WebTrackerService()
