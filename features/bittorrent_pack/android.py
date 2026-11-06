"""Android View adapter for BittorrentPack."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.i18n import N
from app.models.task import TaskStatus

if TYPE_CHECKING:
    from .task import BTTask

UI_CLASS = "com.xychr.ghostdownloader.features.bittorrent_pack.BitTorrentUi"

STATE_TEXT = {
    "checking_files": N("TaskState", "校验已有文件"),
    "checking_resume_data": N("TaskState", "检查续传状态"),
    "downloading_metadata": N("TaskState", "获取元数据"),
    "allocating": N("TaskState", "分配文件中"),
    "queued_for_checking": N("TaskState", "等待校验"),
}


def toStatusText(task: BTTask) -> str:
    if task.isSeeding:
        return N("TaskState", "做种中")
    if task.status == TaskStatus.COMPLETED:
        return ""
    return STATE_TEXT.get(task.stateText, "")


def taskFields(task: BTTask) -> dict[str, Any]:
    return {
        "progressMode": "hidden" if task.isSeeding else "determinate",
        "statusText": toStatusText(task),
        "secondarySpeed": task.uploadRate,
        "packFields": {
            "peers": {"active": task.peerCount, "total": task.totalPeerCount},
            "shareRatio": task.shareRatioPercent,
            "seedingSeconds": task.seedingTimeSeconds,
            "uploadSpeed": task.uploadRate,
        },
    }


async def trackerListState() -> dict[str, Any]:
    from dataclasses import asdict
    from .config import bittorrentConfig
    from .session import btSession
    from .trackers import trackerList

    return {
        "sources": list(bittorrentConfig.webTrackerSources.value),
        "defaults": list(bittorrentConfig.webTrackerSources.defaultValue),
        "custom": bittorrentConfig.webTrackerCustomList.value,
        "statuses": [asdict(status) for status in trackerList.statuses()],
        "entryCount": trackerList.entryCount(),
        "isRefreshing": trackerList.isRefreshing,
        "dhtNodes": await btSession.probeDhtNodes(),
    }


def setTrackerList(sources: str, custom: str) -> None:
    from app.config.cfg import cfg
    from .config import bittorrentConfig

    cfg.set(bittorrentConfig.webTrackerSources, list(dict.fromkeys(sources.split())))
    cfg.set(bittorrentConfig.webTrackerCustomList, custom)


async def refreshTrackerList() -> dict[str, Any]:
    from .trackers import trackerList

    await trackerList.refresh()
    return await trackerListState()
