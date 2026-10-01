"""Android View adapter for ED2kPack."""
from app.i18n import N

UI_CLASS = "com.xychr.ghostdownloader.features.ed2k_pack.Ed2kUi"


def taskFields(task) -> dict:
    active = task.activePeerCount
    return {
        "progressMode": "hidden" if task.isSeeding else "determinate",
        "statusText": N("TaskState", "做种中") if task.isSeeding else "",
        "secondarySpeed": task.uploadRate,
        "packFields": {
            "peers": None if active is None else {
                "active": active, "total": max(active, task.totalPeerCount),
            },
            "shareRatio": task.shareRatioPercent,
            "seedingSeconds": task.seedingTimeSeconds,
            "uploadSpeed": task.uploadRate,
        },
    }


def bootstrapListByName(name: str):
    from .lists import nodeList, serverList

    return {"servers": serverList, "nodes": nodeList}[name]


def sourcesItemByName(name: str):
    from .config import ed2kConfig

    return {"servers": ed2kConfig.serverListSources, "nodes": ed2kConfig.nodeListSources}[name]


async def bootstrapListState(name: str) -> dict:
    from dataclasses import asdict
    from .session import ed2kSession

    bootstrapList = bootstrapListByName(name)
    network = await ed2kSession.probeNetwork()
    return {
        "sources": list(sourcesItemByName(name).value),
        "defaults": list(sourcesItemByName(name).defaultValue),
        "statuses": [asdict(status) for status in bootstrapList.statuses()],
        "isRefreshing": bootstrapList.isRefreshing,
        "serverConnected": None if network is None else network.isServerConnected,
        "kadNodes": None if network is None else network.kadNodes,
    }


def setBootstrapListSources(name: str, sources: str):
    from app.config.cfg import cfg

    cfg.set(sourcesItemByName(name), list(dict.fromkeys(sources.split())))


async def refreshBootstrapList(name: str) -> dict:
    await bootstrapListByName(name).refresh()
    return await bootstrapListState(name)
