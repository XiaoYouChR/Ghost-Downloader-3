from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from app.bootstrap_list import BootstrapList
from app.config.paths import APP_DATA_DIR

from .config import bittorrentConfig

TRACKER_SCHEMES = {"http", "https", "udp", "ws", "wss"}


def parseTrackers(text: str) -> list[str]:
    return [
        tracker for tracker in text.split()
        if (parts := urlsplit(tracker)).scheme.lower() in TRACKER_SCHEMES and parts.netloc
    ]


def parseTrackerList(data: bytes) -> list[str]:
    trackers = parseTrackers(data.decode("utf-8", errors="ignore"))
    if not trackers:
        raise ValueError("没有有效的 Tracker")
    return trackers


trackerList = BootstrapList(
    APP_DATA_DIR / "bt" / "trackers",
    Path(__file__).parent / "lists" / "trackers.txt",
    lambda: list(bittorrentConfig.webTrackerSources.value),
    parseTrackerList,
)


def mergedTrackers() -> list[str]:
    texts = [path.read_text("utf-8", errors="ignore") for path in trackerList.paths()]
    texts.append(bittorrentConfig.webTrackerCustomList.value)
    return list(dict.fromkeys(tracker for text in texts for tracker in parseTrackers(text)))
