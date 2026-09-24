"""Android View adapter for ED2kPack."""
from app.i18n import N

UI_CLASS = "com.xychr.ghostdownloader.features.ed2k_pack.Ed2kUi"


def taskFields(task) -> dict:
    active = task.activePeerCount
    return {
        "progressMode": "hidden" if task.isSeeding else "determinate",
        "statusText": N("TaskState", "共享中") if task.isSeeding else "",
        "secondarySpeed": task.uploadRate,
        "packFields": {
            "peers": None if active is None else {
                "active": active, "total": max(active, task.totalPeerCount),
            },
            "seedingSeconds": task.seedingTimeSeconds,
            "uploadSpeed": task.uploadRate,
        },
    }
