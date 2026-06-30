from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from app.client import buildClient
from app.config.cfg import cfg

from ..config import bittorrentConfig

TRACKER_SCHEMES = {"http", "https", "udp", "ws", "wss"}


class TrackerService:
    def mergedTrackers(self) -> list[str]:
        cache = dict(bittorrentConfig.webTrackerSourceCache.value)
        customText = bittorrentConfig.webTrackerCustomList.value
        customTrackers = [
            t for t in customText.split()
            if (p := urlsplit(t)).scheme.lower() in TRACKER_SCHEMES and p.netloc
        ]
        return list(dict.fromkeys(
            tracker
            for source in (*cache.values(), customTrackers)
            for tracker in source
            if tracker
        ))

    async def refresh(self) -> tuple[int, int]:
        urls = list(bittorrentConfig.webTrackerSources.value)
        if not urls:
            return 0, 0

        async def fetchOne(sourceUrl: str) -> list[str]:
            normalized = sourceUrl.strip()
            parsed = urlsplit(normalized)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Web Tracker 源地址无效")
            client = buildClient()
            try:
                response = await client.get(normalized)
                response.raise_for_status()
                text = await response.text()
            finally:
                client.close()
            trackers = [
                t for t in text.split()
                if (p := urlsplit(t)).scheme.lower() in TRACKER_SCHEMES and p.netloc
            ]
            if not trackers:
                raise ValueError("Web Tracker 源没有返回有效的 Tracker")
            return trackers

        results = await asyncio.gather(
            *(fetchOne(url) for url in urls),
            return_exceptions=True,
        )

        oldCache = dict(bittorrentConfig.webTrackerSourceCache.value)
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
        return successCount, len(urls)


trackerService = TrackerService()
