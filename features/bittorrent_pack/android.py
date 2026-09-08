"""Android View adapter for BittorrentPack."""


def taskFields(task) -> dict:
    return {
        "upload": task.uploadRate,
        "peers": {"active": task.peerCount, "total": task.totalPeerCount},
        "isSeeding": task.isSeeding,
        "seedingSeconds": task.seedingTimeSeconds,
        "shareRatio": task.shareRatioPercent,
        "stateText": task.stateText,
    }
