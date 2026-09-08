"""Android View adapter for ED2kPack."""


def taskFields(task) -> dict:
    active = task.activePeerCount
    return {
        "upload": task.uploadRate,
        "peers": None if active is None else {
            "active": active, "total": max(active, task.totalPeerCount),
        },
        "isSeeding": task.isSharing,
        "seedingSeconds": task.sharingTimeSeconds,
        "stateText": "sharing" if task.isSharing else "",
    }
