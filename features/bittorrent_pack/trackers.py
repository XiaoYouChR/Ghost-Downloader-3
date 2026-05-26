from collections.abc import Iterable
from urllib.parse import urlsplit

import libtorrent as lt
import niquests

from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies

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

    async with niquests.AsyncSession(headers=DEFAULT_HEADERS.copy(), timeout=30, happy_eyeballs=True) as client:
        client.trust_env = False
        response = await client.get(
            normalizedSource,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        response.raise_for_status()
        trackers = parseTrackerText(response.text)

    if not trackers:
        raise ValueError("Web Tracker 源没有返回有效的 Tracker")

    return trackers
