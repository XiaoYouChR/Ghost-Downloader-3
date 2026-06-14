from collections.abc import Iterable
from urllib.parse import urlsplit

import libtorrent as lt

from app.supports.config import defaultHeaders
from app.supports.utils import buildClient, getProxies

_TRACKER_SCHEMES = {"http", "https", "udp", "ws", "wss"}


def toTrackers(source: str) -> str:
    value = source.strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


def parseTrackerText(text: str) -> list[str]:
    return list(dict.fromkeys(
        tracker for tracker in text.split()
        if (parsed := urlsplit(tracker)).scheme.lower() in _TRACKER_SCHEMES and parsed.netloc
    ))


def mergeTrackers(*groups: "lt.torrent_info | Iterable[str]") -> list[str]:
    def _iter(group):
        if isinstance(group, lt.torrent_info):
            return (str(tracker.url).strip() for tracker in group.trackers())
        return group

    return list(dict.fromkeys(
        tracker
        for group in groups
        for tracker in _iter(group)
        if tracker
    ))


async def fetchWebTrackers(sourceUrl: str) -> list[str]:
    normalizedSource = toTrackers(sourceUrl)
    if not normalizedSource:
        raise ValueError("Web Tracker 源地址无效")

    async with buildClient(getProxies(), headers=defaultHeaders(), timeout=30) as client:
        response = await client.get(normalizedSource)
        response.raise_for_status()
        trackers = parseTrackerText(await response.text())

    if not trackers:
        raise ValueError("Web Tracker 源没有返回有效的 Tracker")

    return trackers
