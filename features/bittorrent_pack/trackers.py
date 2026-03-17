from urllib.parse import urlsplit

import niquests

from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies


_TRACKER_SCHEMES = {"http", "https", "udp", "ws", "wss"}


def normalizeTrackerSource(source: str) -> str:
    value = str(source or "").strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


def parseTrackerText(text: str) -> list[str]:
    trackers: list[str] = []
    for raw in str(text or "").replace("\r", "\n").split():
        tracker = raw.strip()
        if not tracker:
            continue
        parsed = urlsplit(tracker)
        if parsed.scheme.lower() not in _TRACKER_SCHEMES or not parsed.netloc:
            continue
        if tracker not in trackers:
            trackers.append(tracker)
    return trackers


def formatTrackers(trackers: list[str]) -> str:
    return "\n".join(parseTrackerText("\n".join(trackers)))


def mergeTrackers(*trackerGroups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in trackerGroups:
        for tracker in group:
            if tracker and tracker not in merged:
                merged.append(tracker)
    return merged


async def fetchWebTrackers(sourceUrl: str) -> list[str]:
    normalizedSource = normalizeTrackerSource(sourceUrl)
    if not normalizedSource:
        raise ValueError("Web Tracker 源地址无效")

    client = niquests.AsyncSession(headers=DEFAULT_HEADERS.copy(), timeout=30, happy_eyeballs=True)
    client.trust_env = False

    # 像极了 Bilibili Pack, 这里在 nuitka 编译后 response.close() 也会导致没有报错的异常

    try:
        response = await client.get(
            normalizedSource,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        response.raise_for_status()
        trackers = parseTrackerText(response.text)
    finally:
        await client.close()

    if not trackers:
        raise ValueError("Web Tracker 源没有返回有效的 Tracker")

    return trackers
