"""Android View adapter for BittorrentPack."""
from app.i18n import N

UI_CLASS = "com.xychr.ghostdownloader.packs.BitTorrentUi"

STATE_TEXT = {
    "checking_files": N("TaskState", "校验已有文件"),
    "checking_resume_data": N("TaskState", "检查续传状态"),
    "downloading_metadata": N("TaskState", "获取元数据"),
    "allocating": N("TaskState", "分配文件中"),
    "queued_for_checking": N("TaskState", "等待校验"),
    "seeding": N("TaskState", "做种中"),
    "paused_seeding": N("TaskState", "暂停做种"),
}


def taskFields(task) -> dict:
    return {
        "progressMode": "hidden" if task.isSeeding else "determinate",
        "statusText": STATE_TEXT.get(task.stateText, ""),
        "secondarySpeed": task.uploadRate,
        "canStop": task.isSeeding,
        "canPause": not task.isSeeding,
        "packFields": {
            "peers": {"active": task.peerCount, "total": task.totalPeerCount},
            "shareRatio": task.shareRatioPercent,
            "seedingSeconds": task.seedingTimeSeconds,
            "uploadSpeed": task.uploadRate,
        },
    }
