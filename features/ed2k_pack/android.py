"""Android View adapter for ED2kPack."""
from app.i18n import N

UI_CLASS = "com.xychr.ghostdownloader.packs.Ed2kUi"


def taskFields(task) -> dict:
    active = task.activePeerCount
    return {
        "progressMode": "hidden" if task.isSharing else "determinate",
        "statusText": N("TaskState", "共享中") if task.isSharing else "",
        "secondarySpeed": task.uploadRate,
        "canPause": not task.isSharing,
        "packFields": {
            "peers": None if active is None else {
                "active": active, "total": max(active, task.totalPeerCount),
            },
            "seedingSeconds": task.sharingTimeSeconds,
            "uploadSpeed": task.uploadRate,
        },
    }
