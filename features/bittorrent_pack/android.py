"""Android View adapter for BittorrentPack."""
from app.i18n import N
from app.models.task import TaskStatus

UI_CLASS = "com.xychr.ghostdownloader.features.bittorrent_pack.BitTorrentUi"

STATE_TEXT = {
    "checking_files": N("TaskState", "校验已有文件"),
    "checking_resume_data": N("TaskState", "检查续传状态"),
    "downloading_metadata": N("TaskState", "获取元数据"),
    "allocating": N("TaskState", "分配文件中"),
    "queued_for_checking": N("TaskState", "等待校验"),
}


def toStatusText(task) -> str:
    if task.isSeeding:
        return N("TaskState", "做种中")
    if task.status == TaskStatus.COMPLETED:
        return ""
    return STATE_TEXT.get(task.stateText, "")


def taskFields(task) -> dict:
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


def setWebTrackerSources(sources: str):
    from app.config.cfg import cfg
    from .config import bittorrentConfig

    urls = list(dict.fromkeys(u.strip() for u in sources.split("\n") if u.strip()))
    cfg.set(bittorrentConfig.webTrackerSources, urls)


async def refreshWebTrackers():
    from .web_tracker.service import trackerService

    await trackerService.refresh()
